"""
Project C, Phase C3 - model supply-chain integrity.

Records a SHA-256 digest of each trusted Ollama model into a manifest, then
verifies a model against the manifest before use and refuses on mismatch
(fail-closed). A tampered-manifest simulation shows the check actually fires.

Digest is computed over the model's own weight blobs on disk (the layers its
Ollama manifest references), not over Ollama's self-reported ID, so tampering
with a blob is detected even if metadata is left untouched.

Ollama store layout (default): ~/.ollama/models
  manifests/registry.ollama.ai/library/<name>/<tag>   (JSON: layer digests)
  blobs/sha256-<hex>                                   (the actual layer data)

Runs fully on-device.

Usage:
  python security/hardening/model_integrity.py build     # write manifest
  python security/hardening/model_integrity.py verify    # check all models
  python security/hardening/model_integrity.py tamper-demo
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE     = Path(__file__).resolve().parent
RESULTS  = HERE / "results"
MANIFEST = HERE / "model_manifest.json"

OLLAMA_ROOT = Path.home() / ".ollama" / "models"
MANIFEST_DIR = OLLAMA_ROOT / "manifests" / "registry.ollama.ai" / "library"
BLOBS_DIR    = OLLAMA_ROOT / "blobs"

# The trusted models this project actually uses (mistral is excluded).
TRUSTED_MODELS = [
    ("llama3.2", "3b"),
    ("llama3.2", "3b-instruct-q5_K_M"),
    ("llama3.2", "3b-instruct-q6_K"),
    ("llama3.2", "3b-instruct-q8_0"),
    ("nomic-embed-text", "latest"),
]


def model_manifest_path(name, tag):
    return MANIFEST_DIR / name / tag


def blob_path(digest_ref):
    # digest_ref looks like 'sha256:abcd...'; on disk it's 'sha256-abcd...'
    return BLOBS_DIR / digest_ref.replace(":", "-")


def layer_digests(name, tag):
    """Return the ordered list of blob digest refs this model is built from."""
    mpath = model_manifest_path(name, tag)
    if not mpath.exists():
        raise FileNotFoundError(f"Ollama manifest not found: {mpath}")
    data = json.loads(mpath.read_text())
    refs = []
    if "config" in data and data["config"].get("digest"):
        refs.append(data["config"]["digest"])
    for layer in data.get("layers", []):
        refs.append(layer["digest"])
    return refs


def compute_model_digest(name, tag):
    """
    SHA-256 over the concatenation of this model's blob contents, in manifest
    order. Reads blobs in chunks so large weight files are streamed, not loaded.
    """
    h = hashlib.sha256()
    total_bytes = 0
    for ref in layer_digests(name, tag):
        bpath = blob_path(ref)
        if not bpath.exists():
            raise FileNotFoundError(f"Blob missing for {name}:{tag}: {bpath.name}")
        h.update(ref.encode("utf-8"))          # bind order + identity
        with bpath.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
                total_bytes += len(chunk)
    return h.hexdigest(), total_bytes


def cmd_build():
    entries = {}
    print("Building trusted-model manifest ...\n")
    for name, tag in TRUSTED_MODELS:
        digest, nbytes = compute_model_digest(name, tag)
        key = f"{name}:{tag}"
        entries[key] = {"sha256": digest, "bytes": nbytes,
                        "layers": layer_digests(name, tag)}
        print(f"  {key:32s} {digest[:16]}...  ({nbytes/1e9:.2f} GB)")

    manifest = {
        "schema": "splaim-model-manifest/1",
        "note": "SHA-256 over each model's on-disk weight blobs, in manifest order.",
        "models": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nWrote manifest -> {MANIFEST}  ({len(entries)} models)")


def verify_all(manifest_path=MANIFEST, verbose=True):
    """Recompute each model's digest and compare to the manifest. Fail-closed."""
    manifest = json.loads(Path(manifest_path).read_text())
    recorded = manifest["models"]
    all_ok = True
    rows = []
    for key, rec in recorded.items():
        name, tag = key.split(":", 1)
        try:
            actual, _ = compute_model_digest(name, tag)
        except FileNotFoundError as e:
            actual = None
            reason = str(e)
        ok = (actual is not None and actual == rec["sha256"])
        all_ok = all_ok and ok
        status = "OK" if ok else "MISMATCH"
        rows.append((key, status))
        if verbose:
            if ok:
                print(f"  [OK]       {key}")
            elif actual is None:
                print(f"  [BLOCKED]  {key}  - {reason}")
            else:
                print(f"  [BLOCKED]  {key}  - digest mismatch")
                print(f"             expected {rec['sha256'][:24]}...")
                print(f"             actual   {actual[:24]}...")
    return all_ok, rows


def cmd_verify():
    if not MANIFEST.exists():
        print("No manifest. Run 'build' first.")
        sys.exit(1)
    print("Verifying models against trusted manifest ...\n")
    ok, _ = verify_all()
    print()
    if ok:
        print("All trusted models verified. Safe to load.")
    else:
        print("VERIFICATION FAILED - refusing to run on unverified weights (fail-closed).")
        sys.exit(2)


def cmd_tamper_demo():
    """
    Show the check fires. We do NOT touch real weights. Instead we copy the
    manifest, flip one recorded digest to simulate a tampered/forged record,
    and show verification blocks that model. Real blobs are untouched.
    """
    RESULTS.mkdir(exist_ok=True)
    if not MANIFEST.exists():
        print("No manifest. Run 'build' first.")
        sys.exit(1)

    lines = []
    def log(s):
        print(s); lines.append(s)

    log("=== Model-integrity tamper demonstration ===")
    log("Real model blobs are NOT modified. We simulate a forged manifest entry")
    log("and confirm verification refuses the affected model (fail-closed).\n")

    good = json.loads(MANIFEST.read_text())

    log("[1] Verify against the GENUINE manifest (expect all OK):")
    ok_good, _ = verify_all(MANIFEST, verbose=True)
    log(f"    result: {'all verified' if ok_good else 'unexpected failure'}\n")

    # Build a tampered copy: flip one hex char of the first model's digest.
    tampered = json.loads(MANIFEST.read_text())
    target = next(iter(tampered["models"]))
    orig = tampered["models"][target]["sha256"]
    flipped = ("f" if orig[0] != "f" else "0") + orig[1:]
    tampered["models"][target]["sha256"] = flipped
    tphath = RESULTS / "model_manifest_tampered.json"
    tphath.write_text(json.dumps(tampered, indent=2) + "\n")

    log(f"[2] Forged a manifest where '{target}' records a wrong digest:")
    log(f"    genuine  {orig[:24]}...")
    log(f"    forged   {flipped[:24]}...")
    log("    Verifying the REAL model against this forged record (expect BLOCKED):")
    ok_bad, rows = verify_all(tphath, verbose=True)
    blocked = [k for k, s in rows if s != "OK"]
    log("")
    log(f"    verification passed overall: {ok_bad}  (expected False)")
    log(f"    blocked models: {blocked}")
    log("")
    if not ok_bad and target in blocked:
        log("Conclusion: a mismatch between recorded and actual weights is detected")
        log("and the model is refused. The integrity check fails closed.")
    else:
        log("UNEXPECTED: the tamper was not caught - investigate before relying on this.")

    out = RESULTS / "integrity_demo.txt"
    out.write_text("\n".join(lines) + "\n")
    print(f"\nSaved -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "verify", "tamper-demo"])
    args = ap.parse_args()
    {"build": cmd_build, "verify": cmd_verify, "tamper-demo": cmd_tamper_demo}[args.command]()


if __name__ == "__main__":
    main()
