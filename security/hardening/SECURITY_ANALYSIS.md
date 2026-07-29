# Security Analysis: Encryption-at-Rest and Model Supply-Chain Integrity

**Project:** `splaim-local-rag` security extension (`security/hardening/`).

This document closes the two threats left as *proposed* in the `PRIVACY_ANALYSIS.md`
threat model: an unencrypted vector store on local disk, and unverified (and so
potentially tampered) model weights. Unlike the prompt-injection and leakage
extensions, this is a build-the-mitigation project: each control is implemented
and then shown to work.

---

## 1. Threats

**Unencrypted vector store.** ChromaDB persists documents and embeddings as
plaintext on local disk. On a lost or stolen device, or under any local account
with read access, the entire corpus (including anything redaction missed) is
readable directly from the store, with no attacker effort beyond opening files.

**Unverified model weights.** Models are pulled from a registry as opaque blobs.
A tampered or backdoored blob, whether from a compromised registry, a
man-in-the-middle fetch, or local modification, would execute with full trust
inside the pipeline. Without an integrity check there is nothing that would
notice the substitution.

---

## 2. Control 1: encryption at rest

The private collection (ids, documents, embeddings, metadatas) is exported to a
single in-memory blob and encrypted to disk with **AES-256-GCM** under a key
derived from a passphrase via **PBKDF2-HMAC-SHA256** (200,000 iterations, random
16-byte salt). GCM is authenticated encryption, so it provides confidentiality
and tamper-detection in one construction. The plaintext export is never written
to disk; only the encrypted container is (`encrypt_store.py`).

Container layout: `magic | salt(16) | nonce(12) | ciphertext(+16-byte GCM tag)`.

**Demonstrated** (`results/encryption_demo.txt`): the raw file does not parse as
JSON and is opaque ciphertext after the fixed magic header; decryption with a
wrong passphrase fails with an `InvalidTag` error; decryption with the correct
passphrase round-trips all 487 documents at 768-dimensional embeddings. The
encrypted file is exactly 54 bytes larger than the plaintext, matching the
header, salt, nonce and authentication tag.

---

## 3. Control 2: model supply-chain integrity

Each trusted model's SHA-256 digest is recorded into a manifest
(`model_manifest.json`). The digest is computed over the model's own weight
blobs on disk, in the order its Ollama manifest references them, rather than
over Ollama's self-reported ID, so a modified blob is detected even if metadata
is left intact. A verifier recomputes each digest before use and refuses to run
on any mismatch (`model_integrity.py`).

The trusted set is the five models the pipeline uses: `llama3.2:3b` and its
q5_K_M, q6_K and q8_0 quantisations, plus `nomic-embed-text`.

**Demonstrated** (`results/integrity_demo.txt`): all five models verify against
the genuine manifest. A forged manifest, with a single recorded digest altered,
causes the affected model to be blocked on digest mismatch while the others
still pass, and overall verification returns failure. The check fails closed:
the default on any mismatch or missing blob is refusal, not silent continuation.
Real weight blobs are never modified in the demonstration.

---

## 4. Control 3: access-control hardening

The sensitive artefacts are restricted to owner-only POSIX permissions
(`harden_permissions.py`, evidence in `results/permissions_report.txt`): the
encrypted container and the integrity manifest to `600`, and the plaintext
private store directory to `700`. This is defence in depth: encryption protects
the confidentiality of the data itself, while permissions reduce the local
attack surface around the key-management and integrity controls, for instance
stopping another local account from reading the ciphertext or editing recorded
digests.

---

## 5. Key finding

Both residual threats in the analysis are now closed with implemented,
demonstrated controls rather than proposals. Confidentiality of the store rests
on authenticated encryption with a passphrase-derived key; integrity of the
model supply chain rests on a fail-closed digest check; and both are backstopped
by owner-only permissions. The design keeps the passphrase and plaintext off
disk, and roots model trust in the actual weight bytes rather than in registry
metadata.

---

## 6. Limitations

- **Passphrase management.** Security reduces to the passphrase. It is never
  stored, which is deliberate, but that means loss of the passphrase means loss
  of the store. A production system would integrate an OS keychain or a KMS.
- **Key derivation cost.** 200k PBKDF2 iterations resist brute force but are not
  memory-hard; a stronger deployment would use scrypt or Argon2id.
- **Trust on first use.** The manifest records whatever is on disk when it is
  built, so integrity is anchored to that moment. Binding it to publisher
  signatures (signed model cards) would extend trust upstream of the local disk.
- **Plaintext store still present.** The original `chroma_db_private/` remains on
  disk (permission-restricted) for pipeline use; a full deployment would serve
  the pipeline from the decrypted-in-memory store and remove the plaintext copy.

---

## 7. Reproduce

```bash
python security/hardening/encrypt_store.py encrypt
python security/hardening/encrypt_store.py demo
python security/hardening/model_integrity.py build
python security/hardening/model_integrity.py verify
python security/hardening/model_integrity.py tamper-demo
python security/hardening/harden_permissions.py apply
```
