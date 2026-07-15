"""
Query the local RAG system.
Retrieval (ChromaDB) + generation (Ollama) run entirely on-device.

Usage:
  python src/query.py "your question here"
  python src/query.py "your question" --model mistral --k 5
  python src/query.py            # interactive mode
"""

import argparse
import time
from pathlib import Path
import ollama
import chromadb

# ---- Config -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR       = PROJECT_ROOT / "chroma_db"
COLLECTION   = "splaim_corpus"
EMBED_MODEL  = "nomic-embed-text"
GEN_MODEL    = "llama3.2:3b"   # default generator
TOP_K        = 4
# ------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a careful research assistant. Answer the user's question using "
    "ONLY the numbered context passages provided. If the answer is not "
    "contained in the context, say clearly: 'The provided documents do not "
    "contain this information.' Cite the passages you use like [1], [2]. "
    "Be concise and accurate."
)


def embed_query(text: str):
    resp = ollama.embeddings(model=EMBED_MODEL, prompt=f"search_query: {text}")
    return resp["embedding"]


def retrieve(coll, question: str, k: int):
    q_emb = embed_query(question)
    res = coll.query(query_embeddings=[q_emb], n_results=k)
    docs  = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    return list(zip(docs, metas, dists))


def build_context(hits):
    blocks = []
    for i, (doc, meta, dist) in enumerate(hits, start=1):
        blocks.append(f"[{i}] (source: {meta['source']})\n{doc}")
    return "\n\n".join(blocks)


def answer(question: str, model: str, k: int):
    client = chromadb.PersistentClient(path=str(DB_DIR))
    coll = client.get_collection(COLLECTION)

    hits = retrieve(coll, question, k)
    context = build_context(hits)

    user_msg = (
        f"Context passages:\n\n{context}\n\n"
        f"Question: {question}\n\nAnswer (cite passages as [n]):"
    )

    t0 = time.time()
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print(f"QUESTION: {question}")
    print(f"MODEL: {model}   |   top-k: {k}   |   gen time: {elapsed:.1f}s")
    print("=" * 70)
    print(resp["message"]["content"].strip())
    print("\n" + "-" * 70)
    print("SOURCES RETRIEVED:")
    for i, (doc, meta, dist) in enumerate(hits, start=1):
        print(f"  [{i}] {meta['source']}  (chunk {meta['chunk']}, distance {dist:.3f})")
    print("-" * 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="Your question (omit for interactive mode)")
    ap.add_argument("--model", default=GEN_MODEL, help="Ollama model for generation")
    ap.add_argument("--k", type=int, default=TOP_K, help="Number of chunks to retrieve")
    args = ap.parse_args()

    if args.question:
        answer(args.question, args.model, args.k)
    else:
        print("Interactive mode. Type a question, or 'quit' to exit.")
        while True:
            q = input("\n> ").strip()
            if q.lower() in {"quit", "exit", "q", ""}:
                break
            answer(q, args.model, args.k)


if __name__ == "__main__":
    main()
