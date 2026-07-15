"""
Phase 3 — Quantization benchmark for the local RAG pipeline (expanded).

Method: retrieval is held FIXED (same embedder, same retrieved context per
question); only the generation model's quantization level varies. Any change
in output is therefore attributable to quantization alone.

Speed: tokens/sec = eval_count / eval_duration (Ollama native metrics),
which measures pure generation and EXCLUDES model load time.

Quality (transparent proxy): keyword-recall against reference concepts for
15 in-domain questions. Matching normalizes case and hyphenation and uses
word STEMS to capture morphological/formatting variants (e.g. "retriev"
matches retrieval/retrieve). Refusal behaviour is measured separately over
3 out-of-domain questions. A rigorous evaluation would use an LLM-judge or
human rating — noted as future work.

Outputs:
  results/benchmark_raw.csv      one row per (model, question)
  results/benchmark_summary.csv  one row per model
Everything runs on-device.
"""

import csv
import re
from pathlib import Path
import ollama
import chromadb

# ---- Config ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR       = PROJECT_ROOT / "chroma_db"
RESULTS_DIR  = PROJECT_ROOT / "results"
COLLECTION   = "splaim_corpus"
EMBED_MODEL  = "nomic-embed-text"
TOP_K        = 4

MODELS = {
    "Q4_K_M": "llama3.2:3b",
    "Q5_K_M": "llama3.2:3b-instruct-q5_K_M",
    "Q6_K":   "llama3.2:3b-instruct-q6_K",
    "Q8_0":   "llama3.2:3b-instruct-q8_0",
}

SYSTEM_PROMPT = (
    "You are a careful research assistant. Answer the user's question using "
    "ONLY the numbered context passages provided. If the answer is not "
    "contained in the context, say clearly: 'The provided documents do not "
    "contain this information.' Cite the passages you use like [1], [2]. "
    "Be concise and accurate."
)

QUESTIONS = [
    # --- RAG (Lewis 2020 + Gao survey) ---
    {"q": "What is retrieval-augmented generation and why is it useful?",
     "keywords": ["retriev", "extern", "knowledge", "generat", "factual"], "type": "in_domain"},
    {"q": "What are the main components or stages of a RAG system?",
     "keywords": ["retriev", "generat", "index", "augment", "embed"], "type": "in_domain"},
    {"q": "How does RAG help reduce hallucination or factually incorrect output?",
     "keywords": ["retriev", "extern", "knowledge", "factual", "hallucin"], "type": "in_domain"},
    {"q": "What is non-parametric memory in the RAG model of Lewis et al.?",
     "keywords": ["non-parametric", "memory", "retriev", "index"], "type": "in_domain"},
    {"q": "How does RAG differ from simply fine-tuning a language model?",
     "keywords": ["retriev", "fine-tun", "knowledge", "updat", "extern"], "type": "in_domain"},
    # --- QLoRA ---
    {"q": "What is 4-bit NormalFloat (NF4) and what is it used for in QLoRA?",
     "keywords": ["4-bit", "normalfloat", "nf4", "quantiz", "weight"], "type": "in_domain"},
    {"q": "What is double quantization in QLoRA?",
     "keywords": ["double", "quantiz", "constant", "memory"], "type": "in_domain"},
    {"q": "What are paged optimizers in QLoRA used for?",
     "keywords": ["paged", "optim", "memory", "spike"], "type": "in_domain"},
    {"q": "What is the main achievement of QLoRA in terms of memory efficiency?",
     "keywords": ["65b", "single", "gpu", "finetun", "memory"], "type": "in_domain"},
    # --- LLM.int8() ---
    {"q": "What problem does LLM.int8() address when running large transformer models?",
     "keywords": ["8-bit", "int8", "matrix", "outlier", "memory"], "type": "in_domain"},
    {"q": "What are outlier features in the context of LLM.int8()?",
     "keywords": ["outlier", "feature", "dimension", "8-bit"], "type": "in_domain"},
    # --- GPTQ ---
    {"q": "How does GPTQ perform post-training quantization of large language models?",
     "keywords": ["post-training", "quantiz", "weight", "layer", "accura"], "type": "in_domain"},
    {"q": "To what precision can GPTQ compress model weights?",
     "keywords": ["quantiz", "bit", "weight", "compress", "precision"], "type": "in_domain"},
    # --- Carlini privacy ---
    {"q": "What privacy risk do Carlini et al. demonstrate about large language models?",
     "keywords": ["training", "data", "extract", "memoriz", "privacy"], "type": "in_domain"},
    {"q": "What is training data memorization according to Carlini et al.?",
     "keywords": ["memoriz", "train", "verbatim", "sequence", "extract"], "type": "in_domain"},
    # --- Out of domain (correct behaviour = refusal) ---
    {"q": "What is the capital of Sweden and who won the 2018 World Cup?",
     "keywords": [], "type": "out_of_domain"},
    {"q": "What is the current price of Bitcoin in US dollars?",
     "keywords": [], "type": "out_of_domain"},
    {"q": "Can you give me a recipe for traditional Swedish meatballs?",
     "keywords": [], "type": "out_of_domain"},
]
# -----------------------------------------------------------------------


def _norm(s):
    """Lowercase and strip hyphens so formatting variants match."""
    return re.sub(r"-", "", s.lower())


def embed_query(text):
    resp = ollama.embeddings(model=EMBED_MODEL, prompt=f"search_query: {text}")
    return resp["embedding"]


def retrieve(coll, question, k):
    q_emb = embed_query(question)
    res = coll.query(query_embeddings=[q_emb], n_results=k)
    docs, metas = res["documents"][0], res["metadatas"][0]
    blocks = [f"[{i}] (source: {m['source']})\n{d}"
              for i, (d, m) in enumerate(zip(docs, metas), start=1)]
    return "\n\n".join(blocks)


def keyword_recall(answer, keywords):
    if not keywords:
        return None
    a = _norm(answer)
    hits = sum(1 for kw in keywords if _norm(kw) in a)
    return hits / len(keywords)


def refused(answer):
    return "do not contain this information" in answer.lower()


def get_model_size_gb(tag):
    try:
        for m in ollama.list()["models"]:
            name = m.get("model") or m.get("name")
            if name == tag:
                return round(m["size"] / 1e9, 2)
    except Exception:
        pass
    return None


def unload(tag):
    try:
        ollama.generate(model=tag, prompt="", keep_alive=0)
    except Exception:
        pass


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(DB_DIR))
    coll = client.get_collection(COLLECTION)

    n_in  = sum(1 for x in QUESTIONS if x["type"] == "in_domain")
    n_ood = sum(1 for x in QUESTIONS if x["type"] == "out_of_domain")
    print(f"Retrieving fixed context for {len(QUESTIONS)} questions "
          f"({n_in} in-domain, {n_ood} out-of-domain) ...")
    contexts = {x["q"]: retrieve(coll, x["q"], TOP_K) for x in QUESTIONS}
    print(f"  {len(contexts)} contexts cached.\n")

    raw_rows = []
    for label, tag in MODELS.items():
        size_gb = get_model_size_gb(tag)
        print(f"=== {label}  ({tag})  size={size_gb} GB ===")
        for item in QUESTIONS:
            q = item["q"]
            user_msg = (f"Context passages:\n\n{contexts[q]}\n\n"
                        f"Question: {q}\n\nAnswer (cite passages as [n]):")
            resp = ollama.chat(
                model=tag,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user_msg}],
            )
            answer = resp["message"]["content"].strip()

            eval_count = resp.get("eval_count", 0) or 0
            eval_dur   = resp.get("eval_duration", 0) or 0
            load_dur   = resp.get("load_duration", 0) or 0
            total_dur  = resp.get("total_duration", 0) or 0
            tok_per_s  = eval_count / (eval_dur / 1e9) if eval_dur else 0

            if item["type"] == "out_of_domain":
                quality = ""                       # not a recall question
                did_refuse = refused(answer)
            else:
                quality = keyword_recall(answer, item["keywords"])
                did_refuse = refused(answer)

            raw_rows.append({
                "model": label, "tag": tag, "size_gb": size_gb,
                "question": q, "type": item["type"],
                "tokens_per_sec": round(tok_per_s, 1),
                "eval_tokens": eval_count,
                "gen_time_s": round(eval_dur / 1e9, 2),
                "load_time_s": round(load_dur / 1e9, 2),
                "total_time_s": round(total_dur / 1e9, 2),
                "answer_words": len(answer.split()),
                "quality": round(quality, 3) if isinstance(quality, float) else "",
                "refused": did_refuse,
            })
            if item["type"] == "in_domain":
                print(f"  [in ] {tok_per_s:5.1f} tok/s  q={quality:.2f}  {q[:46]}...")
            else:
                print(f"  [ood] {tok_per_s:5.1f} tok/s  refused={did_refuse}  {q[:40]}...")
        unload(tag)
        print()

    # Raw CSV
    raw_path = RESULTS_DIR / "benchmark_raw.csv"
    with open(raw_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(raw_rows[0].keys()))
        w.writeheader(); w.writerows(raw_rows)

    # Summary CSV — in-domain quality and refusal rate reported SEPARATELY
    summary_path = RESULTS_DIR / "benchmark_summary.csv"
    with open(summary_path, "w", newline="") as f:
        fields = ["model", "tag", "size_gb", "avg_tokens_per_sec",
                  "avg_quality_in_domain", "refusal_rate",
                  "avg_gen_time_s", "n_in_domain", "n_ood"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for label, tag in MODELS.items():
            rows = [r for r in raw_rows if r["model"] == label]
            ind  = [r for r in rows if r["type"] == "in_domain"]
            ood  = [r for r in rows if r["type"] == "out_of_domain"]
            speeds = [r["tokens_per_sec"] for r in rows]
            quals  = [r["quality"] for r in ind if r["quality"] != ""]
            refusals = [r["refused"] for r in ood]
            w.writerow({
                "model": label, "tag": tag, "size_gb": rows[0]["size_gb"],
                "avg_tokens_per_sec": round(sum(speeds)/len(speeds), 1),
                "avg_quality_in_domain": round(sum(quals)/len(quals), 3),
                "refusal_rate": round(sum(refusals)/len(refusals), 3),
                "avg_gen_time_s": round(sum(r["gen_time_s"] for r in rows)/len(rows), 2),
                "n_in_domain": len(ind),
                "n_ood": len(ood),
            })

    print("=" * 62)
    print(f"Raw results:     {raw_path}")
    print(f"Summary results: {summary_path}")
    print("=" * 62)
    with open(summary_path) as f:
        print(f.read())


if __name__ == "__main__":
    main()
