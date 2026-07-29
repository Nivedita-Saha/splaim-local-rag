"""
Project C, Phase C4 - access-control hardening.

Restricts filesystem permissions on the sensitive local artefacts so only the
owning user can read them, and records the before/after state as evidence.

Rationale:
  - vector_store.enc      holds the (encrypted) corpus; 600 = owner read/write
                          only, so no group/other user on the machine can even
                          read the ciphertext. Defence in depth alongside AES.
  - model_manifest.json   the integrity root of trust; 600 stops another local
                          user silently editing recorded digests.
  - chroma_db_private/    plaintext store still on disk; 700 on the directory
                          keeps its contents owner-only until it is removed in
                          favour of the encrypted container.

600 = rw for owner, nothing for group/other.  700 = rwx owner only.
Runs on macOS/Linux (POSIX permissions).

Usage:
  python security/hardening/harden_permissions.py apply
"""

import os
import stat
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HERE    = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# (path, octal mode, is_dir, rationale)
TARGETS = [
    (HERE / "vector_store.enc",       0o600, False, "encrypted corpus container"),
    (HERE / "model_manifest.json",    0o600, False, "integrity root of trust"),
    (PROJECT_ROOT / "chroma_db_private", 0o700, True, "plaintext private store (owner-only)"),
]


def mode_str(path):
    return stat.filemode(path.stat().st_mode) + f"  ({oct(path.stat().st_mode & 0o777)})"


def main():
    RESULTS.mkdir(exist_ok=True)
    lines = []
    def log(s):
        print(s); lines.append(s)

    log("=== Access-control hardening ===")
    log("Restricting permissions on sensitive artefacts (owner-only).\n")

    for path, mode, is_dir, why in TARGETS:
        if not path.exists():
            log(f"  [skip] {path.name}: not present ({why})")
            continue
        before = mode_str(path)
        os.chmod(path, mode)
        after = mode_str(path)
        kind = "dir " if is_dir else "file"
        log(f"  [{kind}] {path.name}  ({why})")
        log(f"         before: {before}")
        log(f"         after:  {after}")

    log("")
    log("Rationale: even with AES-256-GCM protecting the store's contents,")
    log("owner-only permissions stop other local accounts from reading the")
    log("ciphertext or editing the integrity manifest. This is defence in depth:")
    log("encryption protects confidentiality of the data, permissions reduce the")
    log("local attack surface around the key-management and integrity controls.")

    out = RESULTS / "permissions_report.txt"
    out.write_text("\n".join(lines) + "\n")
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
