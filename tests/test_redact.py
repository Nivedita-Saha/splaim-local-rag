"""Unit tests for src/redact.py (PII redaction)."""

from src.redact import luhn_valid, redact_text


def test_email_is_masked():
    text = "Contact alice.svensson@kau.se for details."
    redacted, stats = redact_text(text)
    assert "alice.svensson@kau.se" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert stats.get("EMAIL") == 1


def test_valid_card_is_masked():
    text = "Card on file: 4111 1111 1111 1111 please keep private."
    redacted, stats = redact_text(text)
    assert "[REDACTED_CARD]" in redacted
    assert stats.get("CARD") == 1


def test_card_shaped_but_invalid_number_survives():
    text = "Model dimensions row: 1234 5678 9012 3456 across layers."
    redacted, stats = redact_text(text)
    assert "1234 5678 9012 3456" in redacted
    assert "CARD" not in stats


def test_clean_text_is_unchanged():
    text = "Retrieval-augmented generation grounds answers in a corpus."
    redacted, stats = redact_text(text)
    assert redacted == text
    assert stats == {}


def test_luhn_valid_helper():
    assert luhn_valid("4111111111111111") is True
    assert luhn_valid("1234567890123456") is False
