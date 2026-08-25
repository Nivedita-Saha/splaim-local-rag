"""
Egress verification (supporting evidence for the threat analysis).

Instruments Python's socket layer to record every outbound TCP connection the
RAG pipeline attempts, then runs a real query end-to-end. Classifies each
connection as LOCAL (loopback: 127.0.0.1 / ::1 / localhost) or EXTERNAL.

Honest scope: this is an APPLICATION-LEVEL check within the Python process.
It demonstrates the pipeline itself opens only loopback connections (to the
local Ollama server). A fully airtight guarantee would additionally use
OS-level firewalling / network namespaces — named as the stronger control in
the write-up. Runs fully on-device.

Writes results/egress_report.txt.
"""

import socket
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"

connection_log: list[tuple] = []  # (host, port, classification)
LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}  # nosec B104  # not a bind; these are loopback addrs classified as LOCAL by the egress check


def _classify(host):
    return "LOCAL" if str(host) in LOOPBACK else "EXTERNAL"


# ---- Instrument socket.connect BEFORE importing the pipeline ----
_orig_connect = socket.socket.connect


def _logged_connect(self, address):
    try:
        host = address[0]
        port = address[1] if len(address) > 1 else "?"
        connection_log.append((str(host), port, _classify(host)))
    except Exception:
        connection_log.append((str(address), "?", "UNKNOWN"))
    return _orig_connect(self, address)


socket.socket.connect = _logged_connect  # type: ignore[method-assign]  # intentional: patch socket to log egress
# -----------------------------------------------------------------

# Import the query pipeline AFTER patching so its calls are captured
import sys  # noqa: E402  (intentional: import after socket patching)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import query as ragquery  # noqa: E402  (intentional: import after socket patching)


def main():
    RESULTS_DIR.mkdir(exist_ok=True)

    test_q = "What is retrieval-augmented generation and why is it useful?"
    print(f'Running instrumented query:\n  "{test_q}"\n')
    print("=" * 60)
    ragquery.answer(test_q, ragquery.GEN_MODEL, ragquery.TOP_K)
    print("=" * 60)

    # De-duplicate connections (host, port)
    seen = {}
    for host, port, cls in connection_log:
        seen[(host, port)] = cls

    external = [(h, p) for (h, p), c in seen.items() if c == "EXTERNAL"]
    local = [(h, p) for (h, p), c in seen.items() if c == "LOCAL"]

    lines = []
    lines.append("EGRESS VERIFICATION REPORT")
    lines.append("=" * 50)
    lines.append(f"Total connection attempts logged : {len(connection_log)}")
    lines.append(f"Unique endpoints                 : {len(seen)}")
    lines.append(f"  LOCAL (loopback)               : {len(local)}")
    lines.append(f"  EXTERNAL                       : {len(external)}")
    lines.append("")
    lines.append("Local endpoints (expected — the on-device Ollama server):")
    for h, p in sorted(local):
        lines.append(f"  {h}:{p}")
    lines.append("")
    if external:
        lines.append("EXTERNAL endpoints (UNEXPECTED — would indicate egress):")
        for h, p in sorted(external):
            lines.append(f"  {h}:{p}")
    else:
        lines.append("EXTERNAL endpoints: NONE")
        lines.append("  -> No data left the machine during this query.")
    report = "\n".join(lines)

    out = RESULTS_DIR / "egress_report.txt"
    out.write_text(report + "\n")

    print("\n" + report)
    print("\n" + "=" * 50)
    print(f"Report written to: {out}")
    verdict = "PASS — no external egress" if not external else "FAIL — external connection detected"
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
