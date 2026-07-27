"""
Phase A5 - visualise ASR before and after defences.
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
    ("No defence\n(baseline)",   "run_poisoned_none.json"),
    ("Sandbox\n(prompt-level)",  "run_poisoned_sandbox.json"),
    ("Sanitise\n(input filter)", "run_poisoned_sanitise.json"),
    ("Both",                     "run_poisoned_both.json"),
]


def load_asr(fname):
    data = json.loads((RESULTS / fname).read_text())
    return data["asr"] * 100.0   # as a percentage


def main():
    labels = [c[0] for c in CONFIGS]
    values = [load_asr(c[1]) for c in CONFIGS]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = ["#c0392b", "#e67e22", "#27ae60", "#2980b9"]
    bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.6)

    ax.set_ylabel("Attack Success Rate (%)")
    ax.set_title("Indirect prompt-injection: ASR before and after defences\n"
                 "(10 attack variants, Llama 3.2 3B, local RAG)")
    ax.set_ylim(0, 100)

    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 2,
                f"{v:.0f}%", ha="center", va="bottom", fontweight="bold")

    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()

    out = RESULTS / "asr_before_after.png"
    fig.savefig(out, dpi=150)
    print(f"Saved chart -> {out}")


if __name__ == "__main__":
    main()
