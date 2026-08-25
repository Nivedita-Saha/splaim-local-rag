"""
PII redaction for the local RAG ingestion pipeline.

A privacy-preserving pre-processing measure: structured personal identifiers
are detected and masked BEFORE text is embedded into the vector store, so
sensitive data never enters the index in the first place.

Scope (deliberate): regex handles STRUCTURED PII with reliable shapes
(emails, phones, IPs, card/ID numbers). Card matches are additionally
validated with the Luhn checksum, so card-SHAPED but invalid numeric data
(e.g. tables of model dimensions in ML papers) is NOT falsely redacted.
Unstructured PII in free prose (names, addresses) needs named-entity
recognition (NER) and is named as future work.

Runs fully on-device. Importable, or run `python src/redact.py --demo`.
"""

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NATIONAL_ID_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_RE = re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b")
PHONE_INTL_RE = re.compile(r"\+\d[\d\s().-]{7,}\d")
PHONE_US_RE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def luhn_valid(number_str):
    """Return True if the digit string satisfies the Luhn checksum."""
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) != 16:
        return False
    total = 0
    # process right-to-left; double every second digit
    for idx, d in enumerate(reversed(digits)):
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact_text(text):
    """
    Mask structured PII in `text`.
    Returns (redacted_text, stats) where stats maps PII type -> count masked.
    """
    stats = {}
    redacted = text

    def counter(label):
        def _sub(m):
            stats[label] = stats.get(label, 0) + 1
            return f"[REDACTED_{label}]"

        return _sub

    # Email first (so '@' isn't disturbed by later patterns)
    redacted = EMAIL_RE.sub(counter("EMAIL"), redacted)
    redacted = NATIONAL_ID_RE.sub(counter("NATIONAL_ID"), redacted)

    # CARD: only redact if the match passes the Luhn checksum
    def _card_sub(m):
        if luhn_valid(m.group(0)):
            stats["CARD"] = stats.get("CARD", 0) + 1
            return "[REDACTED_CARD]"
        return m.group(0)  # card-shaped but invalid -> leave untouched

    redacted = CARD_RE.sub(_card_sub, redacted)

    redacted = PHONE_INTL_RE.sub(counter("PHONE"), redacted)
    redacted = PHONE_US_RE.sub(counter("PHONE"), redacted)
    redacted = IP_RE.sub(counter("IP"), redacted)
    return redacted, stats


def _demo():
    sample = (
        "Please contact Dr. Alice Svensson at alice.svensson@kau.se or call "
        "+46 54 700 1000 for details. The backup line is (206) 555-0142. "
        "Her employee record 123-45-6789 and card 4111 1111 1111 1111 must "
        "stay private. Server logs came from 192.168.1.42. "
        "Note: the RAG paper reports results on pages 9459-9474, which is NOT "
        "a phone number and should survive redaction. "
        "Also this model-dimension row 1536 2048 2560 4096 is NOT a card and "
        "must survive."
    )
    print("----- BEFORE -----")
    print(sample)
    clean, stats = redact_text(sample)
    print("\n----- AFTER -----")
    print(clean)
    print("\n----- MASKED COUNTS -----")
    if stats:
        for k, v in sorted(stats.items()):
            print(f"  {k}: {v}")
    else:
        print("  (none found)")
    print(f"\nTotal identifiers masked: {sum(stats.values())}")
    print(f"Real card '4111...' masked (expected True): {'[REDACTED_CARD]' in clean}")
    print(f"Page range '9459-9474' survived (expected True): {'9459-9474' in clean}")
    print(
        f"Dimension row '1536 2048 2560 4096' survived (expected True): "
        f"{'1536 2048 2560 4096' in clean}"
    )


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        _demo()
    else:
        print("Usage: python src/redact.py --demo")
