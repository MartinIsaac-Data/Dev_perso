from __future__ import annotations

from spp.common.hashing import canonical_json, feature_hash, sha256_of


def test_canonical_json_is_key_order_independent() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_hash_is_stable_across_key_order() -> None:
    assert sha256_of({"elo_diff": 74.3, "is_home": True}) == sha256_of(
        {"is_home": True, "elo_diff": 74.3}
    )


def test_feature_hash_absorbs_floating_point_noise() -> None:
    # Une différence au quinzième chiffre décimal ne doit pas déclencher une
    # fausse alerte de révision rétroactive.
    a = {"xg": 0.1 + 0.2}
    b = {"xg": 0.30000000000000004}
    assert feature_hash(a) == feature_hash(b)


def test_feature_hash_detects_a_real_revision() -> None:
    assert feature_hash({"xg": 1.54}) != feature_hash({"xg": 1.55})
