"""
Ingest PDFs into a local ChromaDB vector store.
Everything runs on-device: text extraction (pypdf), embedding
(nomic-embed-text via Ollama), and storage (ChromaDB on local disk).
No network calls leave the machine.
"""

import re
import sys
from pathlib import Path

import chromadb
import ollama
from pypdf import PdfReader

# ---- Config -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION = "splaim_corpus"
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 1200  # characters
CHUNK_OVERLAP = 200  # characters
# ------------------------------------------------------------------------


def clean(text: str) -> str:
    """Collapse whitespace so chunks are tidy."""
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, size: int, overlap: int):
    """Split text into overlapping character windows."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start += size - overlap
    return chunks


def embed(text: str):
    """Embed one passage locally via Ollama."""
    resp = ollama.embeddings(model=EMBED_MODEL, prompt=f"search_document: {text}")
    return resp["embedding"]


def main():
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {DATA_DIR}")
        sys.exit(1)

    # Fresh collection each run, cosine similarity for normalized-ish vectors
    client = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    total_chunks = 0
    for pdf in pdfs:
        print(f"\nReading {pdf.name} ...")
        reader = PdfReader(str(pdf))
        full_text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            full_text += " " + page_text
        full_text = clean(full_text)

        chunks = chunk_text(full_text, CHUNK_SIZE, CHUNK_OVERLAP)
        print(f"  {len(reader.pages)} pages -> {len(chunks)} chunks, embedding ...")

        ids, docs, embs, metas = [], [], [], []
        for i, ch in enumerate(chunks):
            ids.append(f"{pdf.stem}_{i}")
            docs.append(ch)
            embs.append(embed(ch))
            metas.append({"source": pdf.name, "chunk": i})
            if (i + 1) % 20 == 0:
                print(f"    embedded {i + 1}/{len(chunks)}")

        coll.add(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
        total_chunks += len(chunks)
        print(f"  stored {len(chunks)} chunks from {pdf.name}")

    print(f"\nDone. {len(pdfs)} documents, {total_chunks} chunks total.")
    print(f"Vector store: {DB_DIR}")
    print(f"Collection count: {coll.count()}")


if __name__ == "__main__":
    main()
