"""
Project B, Phase B5 - visualise extraction-success, unprotected vs protected.
Reads the saved run_*.json result files and produces a bar chart.
"""

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE    = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# (label, result-file) in the order we want them plotted
CONFIGS = [
    ("Unredacted\n(baseline)", "run_unredacted.json"),
    ("Redacted\n(PII masked)", "run_redacted.json"),
]


def load(fname):
    return json.loads((RESULTS / fname).read_text())


def main():
    data   = [load(c[1]) for c in CONFIGS]
    labels = [c[0] for c in CONFIGS]
    values = [d["extraction_success"] * 100.0 for d in data]   # percentage

    fig, ax = plt.subplots(figsize=(7, 4.8))
    colors = ["#c0392b", "#27ae60"]   # red = leaks, green = protected
    bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.6)

    ax.set_ylabel("Extraction-success (%)")
    ax.set_title("PII extraction: leakage before and after redaction\n"
                 "(6 planted canaries x 3 queries, Llama 3.2 3B, local RAG)",
                 pad=16)
    ax.set_ylim(0, 118)          # headroom so the 100% label clears the title
    ax.set_yticks(range(0, 101, 20))

    for bar, v, d in zip(bars, values, data):
        n_rec, n_tot = d["recovered"], d["total"]
        ax.text(bar.get_x() + bar.get_width() / 2, v + 2,
                f"{v:.0f}%\n({n_rec}/{n_tot})",
                ha="center", va="bottom", fontweight="bold")

    # annotate what the residual leak is (placed clear of the 17% label)
    ax.text(1, 40,
            "residual = 1 unstructured\naccess code (regex\nredaction cannot catch)",
            ha="center", va="bottom", fontsize=8, style="italic", color="#555555")

    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()

    out = RESULTS / "leakage_before_after.png"
    fig.savefig(out, dpi=150)
    print(f"Saved chart -> {out}")


if __name__ == "__main__":
    main()
