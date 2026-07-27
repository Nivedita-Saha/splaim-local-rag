# Security Analysis: Indirect Prompt-Injection Red-Team

**Project:** `splaim-local-rag` security extension (`security/prompt_injection/`).

This document extends the threat model in `PRIVACY_ANALYSIS.md` (section 3),
which named *data-poisoning / indirect prompt injection* as a residual threat
of the local RAG pipeline. Here that threat is turned from a named risk into a
measured attack, a defence, and a before/after result.

---

## 1. Threat

A retrieval-augmented pipeline pastes retrieved passages directly into the
model's prompt. If an attacker can place text into the corpus, a malicious
instruction hidden inside a document can reach the model with the same standing
as the system's own instructions once that chunk is retrieved. This is
*indirect* prompt injection: the user never types the attack, the document
carries it. In a local, on-device system the corpus is user-controlled, but the
same risk applies to any shared or ingested source (a downloaded paper, a shared
note, a scraped page).

---

## 2. Method

The harness (`attack.py`) reuses the real pipeline: the same embedder, vector
store and system prompt as `src/query.py`. For each test it builds an isolated
index containing one poisoned carrier document plus benign filler, so retrieval
can surface only the intended injection. Generation is deterministic
(temperature 0, fixed seed) so results are reproducible.

Ten injection variants were tested across five technique families:

| Family | Variants |
|---|---|
| Direct | blunt imperative; polite phrasing |
| Impersonation | fake SYSTEM message; context-boundary spoof; fake numbered passage |
| Social | authority framing; instruction-as-citation |
| Obfuscation | split/assembled payload |
| Exfiltration | full system-prompt disclosure; first-line disclosure |

Every payload is benign and produces a unique, programmatically detectable
marker, so success is scored objectively. **Attack Success Rate (ASR)** is the
fraction of variants where the model obeyed the injected instruction.

Two defences were then applied and re-measured:

- **Sandbox (prompt-level):** the system prompt marks retrieved text as
  untrusted data and instructs the model never to follow instructions inside it.
- **Sanitise (input filtering):** known imperative and impersonation patterns
  are stripped from retrieved chunks before they reach the prompt.

---

## 3. Results

A clean-corpus run (no injections) scored **0/10**, confirming the markers only
fire because of the poison and not by chance. Against the poisoned corpus:

| Condition | ASR |
|---|---|
| No defence (baseline) | 3/10 = 0.30 |
| Sandbox (prompt-level) | 3/10 = 0.30 |
| Sanitise (input filter) | 0/10 = 0.00 |
| Both | 0/10 = 0.00 |

![ASR before and after defences](results/asr_animation.gif)

Three variants succeeded at baseline: the blunt imperative, the context-boundary
spoof, and the split payload. All three share a shape: they ask the model to
*append* a marker, which it treats as harmless formatting. The attacks it
resisted asked it to *replace* its answer or *disclose* its prompt, both of
which the existing "answer using ONLY the context" system prompt already guards
against.

---

## 4. Key finding

The prompt-level sandbox made no difference on its own (ASR unchanged at 0.30).
Telling the model to distrust its context did not stop it obeying injected
formatting instructions. Only input sanitisation, removing the malicious text
before it reached the model, drove ASR to zero. For this pipeline, filtering the
input is a stronger control than instructing the model.

---

## 5. Limitations

- **Signature-based filtering.** The sanitiser matches known injection patterns.
  It cleared every tested attack, but a novel phrasing could evade it; this is
  the standard limitation of signature-based detection and argues for combining
  filtering with model-level and output-level controls.
- **Single small model.** Results are for Llama 3.2 3B. A larger or differently
  tuned model would have a different susceptibility profile; the harness is
  model-agnostic and can be re-run against others.
- **Ten variants.** The set characterises five families but is not exhaustive.
  It is a lower bound on the attack surface, not a proof of coverage.

---

## 6. Reproduce

```bash
python security/prompt_injection/build_corpus.py
python security/prompt_injection/attack.py --corpus clean    --defense none
python security/prompt_injection/attack.py --corpus poisoned  --defense none
python security/prompt_injection/attack.py --corpus poisoned  --defense sandbox
python security/prompt_injection/attack.py --corpus poisoned  --defense sanitise
python security/prompt_injection/attack.py --corpus poisoned  --defense both
python security/prompt_injection/plot_asr.py
python security/prompt_injection/make_animation.py
```
