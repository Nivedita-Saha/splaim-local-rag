"""
Project C, Phase C2 - encryption at rest for the private vector store.

Exports the private ChromaDB collection (ids, documents, embeddings, metadatas)
to a single in-memory blob and encrypts it with AES-256-GCM under a key derived
from a passphrase (PBKDF2-HMAC-SHA256, 200k iterations). Provides decrypt-on-
load, and a demo proving the encrypted file is unreadable without the key.

The passphrase is read from SPLAIM_PASSPHRASE, or prompted for (never stored,
never echoed). Only the encrypted container is written to disk; the plaintext
export exists only in memory.

Container format (single file):
  magic(10) | salt(16) | nonce(12) | ciphertext(+GCM tag)

Runs fully on-device.

Usage:
  python security/hardening/encrypt_store.py encrypt
  python security/hardening/encrypt_store.py decrypt
  python security/hardening/encrypt_store.py demo
"""

import argparse
import getpass
import json
import os
from pathlib import Path

import chromadb
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR       = PROJECT_ROOT / "chroma_db_private"
COLLECTION   = "splaim_corpus_private"

HERE     = Path(__file__).resolve().parent
ENC_PATH = HERE / "vector_store.enc"
RESULTS  = HERE / "results"

MAGIC     = b"SPLAIMENC1"
SALT_LEN  = 16
NONCE_LEN = 12
KDF_ITERS = 200_000


def get_passphrase(prompt="Passphrase: "):
    env = os.environ.get("SPLAIM_PASSPHRASE")
    if env:
        return env.encode("utf-8")
    return getpass.getpass(prompt).encode("utf-8")


def derive_key(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=KDF_ITERS)
    return kdf.derive(passphrase)


def export_collection() -> bytes:
    client = chromadb.PersistentClient(path=str(DB_DIR))
    coll = client.get_collection(COLLECTION)
    got = coll.get(include=["documents", "metadatas", "embeddings"])
    payload = {
        "collection": COLLECTION,
        "count": coll.count(),
        "ids": got["ids"],
        "documents": got["documents"],
        "metadatas": got["metadatas"],
        "embeddings": [list(map(float, e)) for e in got["embeddings"]],
    }
    return json.dumps(payload).encode("utf-8")


def encrypt_bytes(plaintext: bytes, passphrase: bytes) -> bytes:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return MAGIC + salt + nonce + ct


def decrypt_bytes(blob: bytes, passphrase: bytes) -> bytes:
    if blob[:len(MAGIC)] != MAGIC:
        raise ValueError("Not a SPLAIM encrypted store (bad magic header).")
    off = len(MAGIC)
    salt = blob[off:off + SALT_LEN]; off += SALT_LEN
    nonce = blob[off:off + NONCE_LEN]; off += NONCE_LEN
    ct = blob[off:]
    key = derive_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, ct, None)   # raises InvalidTag on wrong key / tamper


def cmd_encrypt():
    plaintext = export_collection()
    passphrase = get_passphrase("Set passphrase to encrypt store: ")
    blob = encrypt_bytes(plaintext, passphrase)
    ENC_PATH.write_bytes(blob)
    print(f"Exported + encrypted collection '{COLLECTION}'")
    print(f"  plaintext size : {len(plaintext):,} bytes (in memory only)")
    print(f"  encrypted file : {ENC_PATH.name}  ({len(blob):,} bytes)")
    print(f"  plaintext written to disk: False")


def cmd_decrypt():
    blob = ENC_PATH.read_bytes()
    passphrase = get_passphrase("Passphrase to decrypt store: ")
    payload = json.loads(decrypt_bytes(blob, passphrase))
    dim = len(payload["embeddings"][0]) if payload["embeddings"] else 0
    print("Decryption OK - store round-tripped.")
    print(f"  documents : {payload['count']}")
    print(f"  embed dim : {dim}")
    print(f"  first id  : {payload['ids'][0] if payload['ids'] else '(none)'}")


def cmd_demo():
    RESULTS.mkdir(exist_ok=True)
    lines = []
    def log(s):
        print(s); lines.append(s)

    if not ENC_PATH.exists():
        print("Run 'encrypt' first.")
        raise SystemExit(1)
    blob = ENC_PATH.read_bytes()

    log("=== Encryption-at-rest demonstration ===")
    log(f"Encrypted file: {ENC_PATH.name}  ({len(blob):,} bytes)")

    head = blob[:24]
    printable = sum(32 <= b < 127 for b in head)
    log("")
    log("[1] Raw file is opaque (not readable as text / JSON):")
    log(f"    first 24 bytes (hex): {head.hex()}")
    log(f"    printable ASCII in those bytes: {printable}/24")
    try:
        json.loads(blob)
        log("    JSON parse of raw file: UNEXPECTEDLY SUCCEEDED")
    except Exception:
        log("    JSON parse of raw file: failed as expected (data is ciphertext)")

    log("")
    log("[2] Decryption with a WRONG passphrase:")
    try:
        decrypt_bytes(blob, b"this-is-the-wrong-passphrase")
        log("    UNEXPECTEDLY SUCCEEDED - this must not happen")
    except InvalidTag:
        log("    failed with InvalidTag as expected - unreadable without the key")

    log("")
    log("[3] Decryption with the CORRECT passphrase:")
    passphrase = get_passphrase("    correct passphrase: ")
    try:
        payload = json.loads(decrypt_bytes(blob, passphrase))
        dim = len(payload["embeddings"][0]) if payload["embeddings"] else 0
        log(f"    OK - recovered {payload['count']} documents, embed dim {dim}")
    except InvalidTag:
        log("    FAILED - passphrase did not match the one used to encrypt")
        raise SystemExit(1)

    log("")
    log("Conclusion: the vector store is AES-256-GCM encrypted at rest. Without")
    log("the passphrase-derived key the contents are unrecoverable, and any")
    log("tampering is detected by the GCM authentication tag.")

    out = RESULTS / "encryption_demo.txt"
    out.write_text("\n".join(lines) + "\n")
    print(f"\nSaved -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["encrypt", "decrypt", "demo"])
    args = ap.parse_args()
    {"encrypt": cmd_encrypt, "decrypt": cmd_decrypt, "demo": cmd_demo}[args.command]()


if __name__ == "__main__":
    main()
