from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from spp.core.time import days_between, ensure_utc, recency_weight, utc_now


def test_utc_now_is_aware() -> None:
    assert utc_now().tzinfo is not None


def test_ensure_utc_converts_offsets() -> None:
    paris = datetime(2026, 9, 20, 20, 0, tzinfo=timezone(timedelta(hours=2)))
    assert ensure_utc(paris) == datetime(2026, 9, 20, 18, 0, tzinfo=UTC)


def test_ensure_utc_rejects_naive() -> None:
    with pytest.raises(ValueError, match="naïf"):
        ensure_utc(datetime(2026, 9, 20, 18, 0))  # noqa: DTZ001 - volontaire


def test_days_between() -> None:
    a = datetime(2026, 9, 10, tzinfo=UTC)
    b = datetime(2026, 9, 20, tzinfo=UTC)
    assert days_between(a, b) == pytest.approx(10.0)
    assert days_between(b, a) == pytest.approx(-10.0)


def test_recency_weight_halves_at_half_life() -> None:
    assert recency_weight(90.0, 90.0) == pytest.approx(0.5)
    assert recency_weight(0.0, 90.0) == pytest.approx(1.0)
    assert recency_weight(180.0, 90.0) == pytest.approx(0.25)


def test_recency_weight_rejects_future_matches() -> None:
    with pytest.raises(ValueError, match="futur"):
        recency_weight(-1.0, 90.0)
