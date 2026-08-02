"""The log redaction test (Architecture.md §12.2).

This test exists before there is any content to leak. Personal data in logs is
the kind of defect nobody notices until it is in a third-party log aggregator.
"""

from __future__ import annotations

import pytest

from app.observability.logging import _scrub_processor, redact


@pytest.mark.parametrize(
    ("raw", "must_not_contain"),
    [
        ("contact lea@example.com now", "lea@example.com"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig", "payload"),
    ],
)
def test_redact_removes_identifying_material(raw: str, must_not_contain: str) -> None:
    assert must_not_contain not in redact(raw)


def test_redact_keeps_non_sensitive_text() -> None:
    assert redact("capture.completed in 11842 ms") == "capture.completed in 11842 ms"


@pytest.mark.parametrize(
    "key",
    ["text", "transcript", "title", "body", "email", "access_token", "prompt", "summary"],
)
def test_forbidden_keys_are_scrubbed_whatever_their_value(key: str) -> None:
    event = _scrub_processor(None, "info", {"event": "x", key: "il faut rappeler Paul jeudi"})
    assert event[key] == "[redacted]"


def test_scrubbing_is_case_insensitive_on_keys() -> None:
    event = _scrub_processor(None, "info", {"event": "x", "Transcript": "secret"})
    assert event["Transcript"] == "[redacted]"


def test_allowed_fields_survive() -> None:
    event = _scrub_processor(
        None, "info", {"event": "capture.completed", "capture_id": "018f", "duration_ms": 11842}
    )
    assert event["capture_id"] == "018f"
    assert event["duration_ms"] == 11842


def test_free_text_values_are_still_redacted() -> None:
    event = _scrub_processor(None, "info", {"event": "x", "detail": "user lea@example.com failed"})
    assert "lea@example.com" not in event["detail"]
