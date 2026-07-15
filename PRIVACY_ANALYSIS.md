# Privacy and Threat Analysis: A Local, Privacy-Preserving RAG System

**Project:** `splaim-local-rag` — a fully on-device retrieval-augmented
generation (RAG) pipeline built with Ollama, ChromaDB and a quantized
Llama 3.2 3B model, running on an Apple M2 (8 GB) laptop.

**Purpose of this document:** to analyse the privacy and security properties
of local LLM deployment, compare its threat surface against cloud-hosted
alternatives, model the residual risks that remain even when inference is
local, and describe one implemented privacy-preserving measure. This directly
addresses the SPLAIM themes of *security and privacy risks in locally deployed
AI*, *privacy-preserving inference*, and *threat modelling*.

---

## 1. System overview and data-flow

The pipeline has four stages, all executed on-device:

1. **Ingestion** — text is extracted from local PDFs (`pypdf`).
2. **Redaction** — structured personal identifiers are masked (see §5).
3. **Embedding** — each text chunk is embedded locally by `nomic-embed-text`
   running inside Ollama.
4. **Retrieval + generation** — a query is embedded, the nearest chunks are
   retrieved from a local ChromaDB store, and a local Llama 3.2 3B model
   generates a grounded answer.

The corpus comprises 6 open-access papers (487 chunks). No component calls an
external API: embeddings, the vector store, and generation are all local. This
is the fundamental privacy property — the retrieval-augmented approach of
Lewis et al. (2020) is realised without exposing documents or queries to any
third party.

### Empirical verification of the no-egress property

Rather than assert that "no data leaves the machine", the claim was tested. The
Python socket layer was instrumented to log every outbound connection during a
complete RAG query (`src/verify_egress.py`). The result: exactly **one**
connection was opened, to `127.0.0.1:11434` — the loopback address of the local
Ollama server — and **zero** external connections. This is application-level
evidence that the pipeline communicates only with on-device services. A
stronger guarantee would add OS-level firewalling or network namespaces; this
is named as the more rigorous control in §6.

---

## 2. Cloud vs. local: comparative threat surface

Sending prompts and documents to a hosted LLM API introduces exposure points
that simply do not exist when inference is local.

| Risk | Cloud-hosted LLM API | Local deployment (this project) |
|---|---|---|
| **Data in transit** | Prompts and documents traverse the network to a third party. | Never leaves the device (§1). |
| **Provider retention** | Inputs may be logged, cached, or retained per provider policy. | No provider; nothing to retain. |
| **Training on user data** | Submitted data may be reused for model training. | Impossible — no data is shared. |
| **Legal / subpoena exposure** | Data on provider servers is reachable by legal process. | Data stays under the user's sole control. |
| **Provider breach** | A breach of the provider exposes all users' data. | No external attack surface of this kind. |
| **Memorization leakage** | A shared model may leak other users' data (see below). | The model is read-only and local. |

The final row is grounded in direct evidence. Carlini et al. (2021) demonstrate
that large language models memorize and can be induced to emit verbatim
sequences from their training data, including personally identifiable
information. This is the concrete reason "trust the provider" is not a security
argument: even a well-intentioned provider operates a model that can leak data,
and pooling many users' inputs into one hosted service enlarges the
consequences of any such leak. Local deployment removes the shared-service
attack surface entirely.

---

## 3. Threat model for the local system

Local deployment is not the same as "zero risk". A credible analysis names the
threats that remain, so that they can be mitigated rather than ignored.

| Threat | Description | Mitigation (current / proposed) |
|---|---|---|
| **Device compromise / theft** | The vector store and documents sit on local disk. | Full-disk encryption (e.g. FileVault); OS access controls. |
| **Unencrypted vector store** | ChromaDB persists embeddings and source text in plaintext on disk. | Encrypt the store at rest; restrict file permissions. |
| **Malicious model weights** | A tampered or backdoored model pulled from a registry could behave adversarially. | Verify checksums; pin trusted model sources. |
| **Data-poisoning / indirect prompt injection** | A malicious instruction hidden in an ingested document could subvert generation. | Treat retrieved context as untrusted; input sanitisation; output constraints. |
| **Residual PII in the index** | Unstructured PII (names, addresses) is not caught by regex redaction. | NER-based redaction (§6). |

Framing local deployment this way reflects the SPLAIM emphasis on threat
modelling: the privacy gains of §2 are real, but they shift the security
burden onto device and supply-chain controls rather than eliminating it.

---

## 4. The quantization trade-off under resource constraints

Because local deployment must run on constrained hardware, model compression is
central. The parameter-efficient and quantization techniques of Dettmers et al.
(2022, 2023) and Frantar et al. (2022) make it feasible to run capable models
on an 8 GB laptop at all.

A controlled benchmark held retrieval fixed and varied only the generator's
quantization level (Q4_K_M → Q8_0). Key findings on the M2 (8 GB):

- **Speed:** Q4 generated ~55% faster than Q8 (39.4 vs. 25.4 tokens/sec).
- **Size:** Q4 is 41% smaller on disk (2.02 vs. 3.42 GB).
- **Quality:** in-domain answer quality (a keyword-recall proxy) spanned only
  0.74–0.85 across all four levels — a spread within measurement noise
  (SE ≈ 0.08 at n = 15), i.e. **no statistically meaningful quality loss** from
  aggressive quantization.
- **Safety behaviour:** refusal of out-of-domain questions was preserved at
  100% across every quantization level.

**Implication:** under resource constraints, the most aggressive quantization
(Q4) is the rational default — it is the fastest and smallest with no reliable
quality penalty. This is a security-relevant result too: cheaper local
inference lowers the barrier to keeping data on-device rather than resorting to
the cloud.

---

## 5. Implemented privacy-preserving measure: PII redaction at ingestion

The concrete measure implemented here masks structured personal identifiers
**before** text is embedded, so sensitive data never enters the vector store
(`src/redact.py`, `src/ingest_private.py`).

- **Coverage:** emails, phone numbers (international and national formats),
  national-ID numbers, payment-card numbers, and IP addresses, via validated
  regular expressions.
- **Precision safeguard:** card detection is gated by the **Luhn checksum**.
  During development, a card-shaped string in a table of model dimensions
  (`1536 2048 2560 4096`) was falsely flagged; adding Luhn validation
  eliminated this false positive while still masking valid card numbers. This
  illustrates the precision/recall trade-off inherent in rule-based privacy
  tooling.
- **Result on the corpus:** across 487 chunks, **4 real author email addresses**
  were masked and no false positives remained (`results/redaction_audit.txt`).

Masking at ingestion (rather than at query time) means the sensitive value is
absent from every downstream stage — embedding, storage, and retrieval — which
is the strongest place in the pipeline to apply the control.

---

## 6. Limitations and future work

- **Unstructured PII.** Regex handles structured identifiers only. Names and
  addresses in free prose require named-entity recognition; a production system
  would combine both. This was deliberately scoped out rather than implemented
  poorly.
- **Egress proof strength.** The verification in §1 is application-level.
  OS-level firewalling or a network namespace would provide a stronger,
  process-independent guarantee.
- **Encryption at rest.** The vector store is currently plaintext on disk;
  encrypting it would close the device-compromise threat in §3.
- **Quality metric.** The keyword-recall proxy is transparent but coarse; an
  LLM-as-judge or human evaluation would measure answer quality more rigorously.

---

## References

Carlini, N., Tramèr, F., Wallace, E., Jagielski, M., Herbert-Voss, A., Lee, K.,
Roberts, A., Brown, T., Song, D., Erlingsson, Ú., Oprea, A. and Raffel, C.
(2021) 'Extracting training data from large language models', *30th USENIX
Security Symposium (USENIX Security 21)*, pp. 2633–2650.

Dettmers, T., Lewis, M., Belkada, Y. and Zettlemoyer, L. (2022) 'LLM.int8():
8-bit matrix multiplication for transformers at scale', *Advances in Neural
Information Processing Systems 35 (NeurIPS 2022)*. arXiv:2208.07339.

Dettmers, T., Pagnoni, A., Holtzman, A. and Zettlemoyer, L. (2023) 'QLoRA:
Efficient finetuning of quantized LLMs', *Advances in Neural Information
Processing Systems 36 (NeurIPS 2023)*. arXiv:2305.14314.

Frantar, E., Ashkboos, S., Hoefler, T. and Alistarh, D. (2022) 'GPTQ: Accurate
post-training quantization for generative pre-trained transformers'.
arXiv:2210.17323.

Gao, Y., Xiong, Y., Gao, X., Jia, K., Pan, J., Bi, Y., Dai, Y., Sun, J., Wang,
M. and Wang, H. (2023) 'Retrieval-augmented generation for large language
models: A survey'. arXiv:2312.10997. [Confirm the full author list against the
PDF before submission.]

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N.,
Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S. and Kiela, D.
(2020) 'Retrieval-augmented generation for knowledge-intensive NLP tasks',
*Advances in Neural Information Processing Systems 33 (NeurIPS 2020)*,
pp. 9459–9474. arXiv:2005.11401.
