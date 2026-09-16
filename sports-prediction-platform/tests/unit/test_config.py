from __future__ import annotations

import pytest
from pydantic import ValidationError
from spp.common.config import Settings


def test_defaults_are_conservative() -> None:
    s = Settings(_env_file=None)
    assert s.kelly_fraction == 0.25
    assert s.max_stake_pct == 0.02
    assert s.min_data_quality == 0.75


def test_near_full_kelly_is_refused() -> None:
    # Miser Kelly complet revient à parier sur sa propre calibration.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, kelly_fraction=0.9)


def test_stake_cap_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_stake_pct=0.5)


def test_cors_origins_are_split() -> None:
    s = Settings(_env_file=None, api_cors_origins="http://a, http://b")
    assert s.cors_origins == ["http://a", "http://b"]
