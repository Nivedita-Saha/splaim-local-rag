"""
Phase 3 — Plot the quantization trade-off from benchmark_summary.csv.
Produces publication-style PNGs in results/:
  - tradeoff_speed_quality.png   speed vs quality, point size ~ model size
  - speed_and_size_bars.png      tokens/sec and on-disk size per model
  - gen_time_by_model.png        avg generation time per model
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"
SUMMARY_CSV = RESULTS_DIR / "benchmark_summary.csv"

# Consistent colour per model across all figures
COLORS = {"Q4_K_M": "#2563eb", "Q5_K_M": "#059669", "Q6_K": "#d97706", "Q8_0": "#dc2626"}


def load_summary():
    rows = []
    with open(SUMMARY_CSV) as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "model": r["model"],
                    "size_gb": float(r["size_gb"]),
                    "tok_s": float(r["avg_tokens_per_sec"]),
                    "quality": float(r["avg_quality_in_domain"]),
                    "refusal": float(r["refusal_rate"]),
                    "gen_time": float(r["avg_gen_time_s"]),
                }
            )
    return rows


def plot_tradeoff(rows):
    fig, ax = plt.subplots(figsize=(8, 6))
    for r in rows:
        ax.scatter(
            r["tok_s"],
            r["quality"],
            s=r["size_gb"] * 120,
            alpha=0.75,
            color=COLORS[r["model"]],
            edgecolors="black",
            linewidths=1.2,
            label=f"{r['model']} ({r['size_gb']} GB)",
        )
        ax.annotate(
            r["model"],
            (r["tok_s"], r["quality"]),
            xytext=(8, 8),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
        )
    ax.set_xlabel("Generation speed (tokens/sec)  →  faster", fontsize=12)
    ax.set_ylabel("In-domain answer quality (keyword-recall proxy)", fontsize=12)
    ax.set_title(
        "Quantization trade-off: speed vs quality\n"
        "Llama 3.2 3B RAG on Apple M2 (8 GB) — bubble size ∝ on-disk size",
        fontsize=12,
    )
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(title="Quantization level", loc="upper left", fontsize=9)
    # pad y so bubbles aren't clipped
    qs = [r["quality"] for r in rows]
    ax.set_ylim(min(qs) - 0.15, max(qs) + 0.12)
    fig.tight_layout()
    out = RESULTS_DIR / "tradeoff_speed_quality.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.name}")


def plot_speed_size_bars(rows):
    models = [r["model"] for r in rows]
    colors = [COLORS[m] for m in models]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.bar(models, [r["tok_s"] for r in rows], color=colors, edgecolor="black", linewidth=1)
    ax1.set_ylabel("Generation speed (tokens/sec)", fontsize=11)
    ax1.set_title("Speed by quantization level", fontsize=12)
    for i, r in enumerate(rows):
        ax1.text(
            i, r["tok_s"] + 0.4, f"{r['tok_s']:.1f}", ha="center", fontsize=10, fontweight="bold"
        )

    ax2.bar(models, [r["size_gb"] for r in rows], color=colors, edgecolor="black", linewidth=1)
    ax2.set_ylabel("On-disk model size (GB)", fontsize=11)
    ax2.set_title("Model size by quantization level", fontsize=12)
    for i, r in enumerate(rows):
        ax2.text(
            i,
            r["size_gb"] + 0.03,
            f"{r['size_gb']:.2f}",
            ha="center",
            fontsize=10,
            fontweight="bold",
        )

    fig.suptitle("Higher precision costs speed and disk — Llama 3.2 3B on M2 (8 GB)", fontsize=13)
    fig.tight_layout()
    out = RESULTS_DIR / "speed_and_size_bars.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.name}")


def plot_gen_time(rows):
    models = [r["model"] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(
        models,
        [r["gen_time"] for r in rows],
        color=[COLORS[m] for m in models],
        edgecolor="black",
        linewidth=1,
    )
    ax.set_ylabel("Avg generation time per answer (s)", fontsize=11)
    ax.set_title(
        "Average generation time by quantization level\nLlama 3.2 3B RAG on Apple M2 (8 GB)",
        fontsize=12,
    )
    for i, r in enumerate(rows):
        ax.text(
            i,
            r["gen_time"] + 0.05,
            f"{r['gen_time']:.2f}s",
            ha="center",
            fontsize=10,
            fontweight="bold",
        )
    fig.tight_layout()
    out = RESULTS_DIR / "gen_time_by_model.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.name}")


def main():
    rows = load_summary()
    # order Q4 -> Q8 for consistent left-to-right reading
    order = ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
    rows.sort(key=lambda r: order.index(r["model"]))
    print("Generating plots ...")
    plot_tradeoff(rows)
    plot_speed_size_bars(rows)
    plot_gen_time(rows)
    print(f"\nAll figures saved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
