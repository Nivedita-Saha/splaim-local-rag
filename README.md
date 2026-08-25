# splaim-local-rag

[![CI](https://github.com/Nivedita-Saha/splaim-local-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/Nivedita-Saha/splaim-local-rag/actions/workflows/ci.yml)

A fully **local, privacy-preserving Retrieval-Augmented Generation (RAG)** system, with a **quantization benchmark** and a **privacy/threat analysis**.
Built to run entirely on-device on an Apple M2 (8 GB) laptop — no cloud APIs,
no data leaving the machine.

This project was developed in the context of the **SPLAIM** doctoral position
(Security and Privacy of Locally-Run AI Models, Karlstad University,
REK2026/128). It is a self-contained study of how a capable LLM can be deployed
**securely, privately, and efficiently under real resource constraints**.

---

## What it does

- Runs a small open-weight model (**Llama 3.2 3B**) locally via **Ollama** — no
  external API is ever called.
- Builds a RAG pipeline over a corpus of open-access papers, with **local
  embeddings** (`nomic-embed-text`) and a **local vector store** (ChromaDB).
- Benchmarks the **quantization trade-off** (Q4 / Q5 / Q6 / Q8) in speed,
  size, and answer quality on 8 GB hardware.
- Implements a **privacy-preserving measure** — PII redaction at ingestion —
  and **empirically verifies** that no data leaves the machine.

---

## Mapping to SPLAIM assessment criteria

| SPLAIM criterion | Where this project addresses it |
|---|---|
| Local LLM deployment (fine-tuning, RAG, quantization, benchmarking) | Local RAG pipeline (`src/query.py`); quantization benchmark (`src/benchmark.py`) |
| Performance efficiency under resource constraints | Full Q4–Q8 sweep on an 8 GB M2; findings in `results/` and §4 of the analysis |
| Security & privacy risks in locally deployed AI | Threat model in `PRIVACY_ANALYSIS.md` §2–3 |
| Privacy-preserving inference / technologies | PII redaction at ingestion (`src/redact.py`, `src/ingest_private.py`) |
| Threat modelling | Cloud-vs-local threat comparison + empirical no-egress verification (`src/verify_egress.py`) |

---

## Key findings

- **Quantization:** Q4 generated ~55% faster than Q8 (39.4 vs. 25.4 tok/s) and
  is 41% smaller on disk, with **no statistically meaningful loss** in
  in-domain answer quality — so under resource constraints, aggressive
  quantization is the rational default.
- **Safety:** refusal of out-of-domain questions held at 100% across all
  quantization levels.
- **Privacy:** PII redaction masked 4 real author emails across the corpus
  before indexing; egress verification recorded connections only to
  `127.0.0.1:11434` (local Ollama) and **zero** external connections.

See `PRIVACY_ANALYSIS.md` for the full privacy and threat analysis, and
`results/` for raw numbers and figures.

---

## Repository layout                                                                                                                                                                                                                       src/
ingest.py           # extract -> chunk -> embed (local) -> store
ingest_private.py   # same pipeline, with PII redaction before embedding
query.py            # retrieve + generate a grounded, cited answer
benchmark.py        # quantization sweep: speed / size / quality / refusal
plot_results.py     # trade-off figures
redact.py           # PII redaction (regex + Luhn-validated cards)
verify_egress.py    # instruments sockets to prove no external egress
results/              # CSVs, figures, redaction + egress reports
PRIVACY_ANALYSIS.md   # privacy & threat analysis (Harvard-referenced)
fetch_corpus.sh       # downloads the open-access paper corpus                                                                                                                                                                          Note: model weights, the corpus PDFs, the virtual environment, and the vector
stores are **excluded from version control** (`.gitignore`). Only reproducible
code and recorded results are committed — the models and corpus are pulled on
demand.

---

## Reproducing

Requires macOS with [Ollama](https://ollama.com) installed.

```bash
# 1. environment
python3 -m venv venv && source venv/bin/activate
pip install ollama chromadb pypdf matplotlib

# 2. models (pulled locally via Ollama)
ollama pull nomic-embed-text
ollama pull llama3.2:3b
ollama pull llama3.2:3b-instruct-q5_K_M
ollama pull llama3.2:3b-instruct-q6_K
ollama pull llama3.2:3b-instruct-q8_0

# 3. corpus + ingestion
bash fetch_corpus.sh
python src/ingest.py            # standard ingestion
python src/ingest_private.py    # privacy-preserving ingestion (PII redaction)

# 4. query, benchmark, verify
python src/query.py "What is retrieval-augmented generation?"
python src/benchmark.py
python src/plot_results.py
python src/verify_egress.py
```

---

## Continuous integration & quality gate

[![CI](https://github.com/Nivedita-Saha/splaim-local-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/Nivedita-Saha/splaim-local-rag/actions/workflows/ci.yml)

Every push and pull request runs an automated quality gate via GitHub Actions
(`.github/workflows/ci.yml`). The pipeline runs on a clean Ubuntu machine with
Python 3.12 and checks the core pipeline (`src/`) in sequence:

- **Linting & formatting** — `ruff check` and `ruff format --check`
- **Type checking** — `mypy src`
- **Security static analysis** — `bandit -r src`
- **Tests** — `pytest` with coverage

A second job builds a **Docker image** (`Dockerfile`) on `python:3.12-slim` and
runs the same gate inside a from-scratch container, verifying the code assembles
and passes in an isolated environment.

### Running the gate locally

```bash
pip install -r requirements-dev.txt   # dev tools, kept separate from runtime deps
ruff check src tests
mypy src
bandit -r src
pytest --cov=src --cov-report=term-missing
```

Or reproduce the containerised gate exactly as CI does:

```bash
docker build -t splaim-local-rag:ci .
docker run --rm splaim-local-rag:ci
```

### Scope and suppressions

The gate is deliberately scoped to `src/` and `tests/`. The exploratory
`security/` red-team scripts are excluded — they are one-off experiments, not
maintained pipeline code. Tests cover the privacy-critical redaction logic
(`redact.py`); coverage of the rest of `src/` is low by design, since the RAG
pipeline needs a live Ollama daemon and local models that are out of scope for CI.

A small number of linter/analyser findings are consciously suppressed with an
inline reason rather than "fixed", because the flagged code is correct in
context:

- `verify_egress.py` imports the pipeline **after** patching `socket.connect`
  (`# noqa: E402`), and patches the method deliberately (`# type: ignore`) — this
  is how the egress test intercepts connections.
- `bandit B104` on the loopback set in `verify_egress.py` is a false positive:
  `0.0.0.0` there is a value in a *classification* set for the egress check, not
  a server bind.
- `bandit B110` on best-effort cleanup/unload calls, where a failure is safe and
  intentionally ignored.

The Docker image builds and runs the gate but does **not** install Ollama or pull
model weights: reproducing the full RAG pipeline requires a host Ollama daemon
and local models, as described under *Reproducing* above.

---

## Security extensions

Beyond the privacy analysis, every threat in the model is addressed directly by
three extensions under `security/`. Two are red-teams that turn a named threat
into a measured attack, a defence, and a before/after result; the third builds
and demonstrates the remaining mitigations.

**Indirect prompt injection** (`security/prompt_injection/`) hides malicious
instructions inside corpus documents and measures how often the model obeys
them, before and after defences.

![Prompt-injection ASR before and after defences](security/prompt_injection/results/asr_animation.gif)

Across 10 attack variants (5 technique families), the baseline attack success
rate was 0.30. Prompt-level sandboxing alone made no difference; input
sanitisation reduced it to 0.00. A clean-corpus control scored 0.00, confirming
the result is caused by the injections. Full method, results and limitations are
in `security/prompt_injection/SECURITY_ANALYSIS.md`.

**PII extraction / leakage** (`security/leakage/`) plants synthetic secret
"canaries" in the corpus and probes whether retrieval can be induced to reveal
them, comparing an unredacted index against one protected by the pipeline's
ingestion-time PII redaction.

![PII extraction-success before and after redaction](security/leakage/results/leakage_before_after.png)

Across 6 planted canaries (each probed with 3 query styles), extraction-success
was 1.00 against the unredacted index and 0.17 against the redacted one:
redaction secured all 5 structured identifiers, and the single residual leak is
one unstructured access code that regex redaction cannot catch, quantifying the
NER limitation noted in the privacy analysis. Full method, results and
limitations are in `security/leakage/SECURITY_ANALYSIS.md`.

**Encryption at rest and model integrity** (`security/hardening/`) closes the
two remaining threats by building the mitigations. The private vector store is
exported and encrypted at rest with AES-256-GCM under a passphrase-derived key,
shown to be unreadable without the key and to round-trip all 487 documents with
it. Each trusted model's SHA-256 digest, computed over its on-disk weight blobs,
is recorded in a manifest, and a fail-closed verifier refuses any model that
does not match, demonstrated against a forged manifest. Owner-only file
permissions back both controls. Full method, results and limitations are in
`security/hardening/SECURITY_ANALYSIS.md`.

---

## Honest limitations

- The quality metric is a transparent keyword-recall proxy; rigorous
  evaluation would use an LLM-judge or human rating.
- PII redaction covers structured identifiers only; unstructured PII (names,
  addresses) needs NER.
- Egress verification is application-level; OS-level firewalling would give a
  stronger guarantee.

These are discussed further in `PRIVACY_ANALYSIS.md`.
