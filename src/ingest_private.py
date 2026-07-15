"""
Privacy-preserving ingestion: identical to ingest.py, but every chunk passes
through PII redaction BEFORE embedding. Structured personal identifiers are
therefore masked before they can enter the vector store.

Reports the total PII masked across the corpus, and writes a short audit file
to results/redaction_audit.txt.

Runs fully on-device.
"""

from pathlib import Path
import re
import sys
import ollama
import chromadb
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact import redact_text

# ---- Config -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
DB_DIR       = PROJECT_ROOT / "chroma_db_private"   # separate store
RESULTS_DIR  = PROJECT_ROOT / "results"
COLLECTION   = "splaim_corpus_private"
EMBED_MODEL  = "nomic-embed-text"
CHUNK_SIZE   = 1200
CHUNK_OVERLAP = 200
# ------------------------------------------------------------------------


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text, size, overlap):
    chunks, start = [], 0
    while start < len(text):
        piece = text[start:start + size].strip()
        if piece:
            chunks.append(piece)
        start += size - overlap
    return chunks


def embed(text):
    resp = ollama.embeddings(model=EMBED_MODEL, prompt=f"search_document: {text}")
    return resp["embedding"]


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {DATA_DIR}")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    corpus_stats = {}
    per_doc = {}
    total_chunks = 0

    for pdf in pdfs:
        print(f"\nReading {pdf.name} ...")
        reader = PdfReader(str(pdf))
        full_text = ""
        for page in reader.pages:
            full_text += " " + (page.extract_text() or "")
        full_text = clean(full_text)

        chunks = chunk_text(full_text, CHUNK_SIZE, CHUNK_OVERLAP)
        print(f"  {len(reader.pages)} pages -> {len(chunks)} chunks")

        ids, docs, embs, metas = [], [], [], []
        doc_masked = 0
        for i, ch in enumerate(chunks):
            redacted, stats = redact_text(ch)      # <-- privacy step
            for k, v in stats.items():
                corpus_stats[k] = corpus_stats.get(k, 0) + v
                doc_masked += v
            ids.append(f"{pdf.stem}_{i}")
            docs.append(redacted)                  # store the REDACTED text
            embs.append(embed(redacted))           # embed the REDACTED text
            metas.append({"source": pdf.name, "chunk": i})
            if (i + 1) % 20 == 0:
                print(f"    embedded {i + 1}/{len(chunks)}")

        coll.add(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
        per_doc[pdf.name] = doc_masked
        total_chunks += len(chunks)
        print(f"  stored {len(chunks)} chunks; PII masked in this doc: {doc_masked}")

    total_masked = sum(corpus_stats.values())

    # ---- audit report ----
    lines = []
    lines.append("PII REDACTION AUDIT — privacy-preserving ingestion")
    lines.append("=" * 55)
    lines.append(f"Documents ingested : {len(pdfs)}")
    lines.append(f"Total chunks       : {total_chunks}")
    lines.append(f"Total PII masked   : {total_masked}")
    lines.append("")
    lines.append("By identifier type:")
    if corpus_stats:
        for k, v in sorted(corpus_stats.items()):
            lines.append(f"  {k:14s}: {v}")
    else:
        lines.append("  (none detected)")
    lines.append("")
    lines.append("By document:")
    for name, cnt in per_doc.items():
        lines.append(f"  {cnt:4d}  {name}")
    report = "\n".join(lines)

    audit_path = RESULTS_DIR / "redaction_audit.txt"
    audit_path.write_text(report + "\n")

    print("\n" + "=" * 55)
    print(report)
    print("=" * 55)
    print(f"\nPrivate vector store: {DB_DIR}")
    print(f"Collection count    : {coll.count()}")
    print(f"Audit written to    : {audit_path}")


if __name__ == "__main__":
    main()
