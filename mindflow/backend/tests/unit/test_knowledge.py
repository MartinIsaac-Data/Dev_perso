"""Entity extraction contract and — the part that actually matters — resolution.

Resolution is where a knowledge graph is won or lost. Merge too eagerly and two
people become one, which is unrecoverable and invisible. Merge too timidly and
« quels sujets reviennent souvent ? » answers "nothing recurs" over a corpus
where everything does.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.knowledge import (
    EntityKind,
    ExtractedEntity,
    KnowledgeExtraction,
    json_schema_for_llm,
    normalise_name,
    resolution_key,
)


def _entity(kind: EntityKind, name: str, confidence: float = 0.9) -> ExtractedEntity:
    return ExtractedEntity(kind=kind, name=name, confidence=confidence)


class TestKinds:
    def test_the_seven_required_kinds_exist(self) -> None:
        assert {kind.value for kind in EntityKind} == {
            "person",
            "product",
            "company",
            "project",
            "decision",
            "risk",
            "action",
        }

    def test_every_kind_has_a_french_label_for_the_ui(self) -> None:
        assert all(kind.label for kind in EntityKind)
        assert EntityKind.RISK.label == "Risque"

    def test_proper_nouns_are_nameable_and_statements_are_not(self) -> None:
        assert EntityKind.PERSON.is_nameable
        assert EntityKind.COMPANY.is_nameable
        assert not EntityKind.DECISION.is_nameable
        assert not EntityKind.RISK.is_nameable


class TestNormaliseName:
    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("Jean-Marc Ondo", "jean marc ondo"),
            ("Théo", "Theo"),
            ("Sylvie  Mba", "Sylvie Mba"),
            ("TOTAL", "total"),
            ("la société Total", "Total"),
            ("le projet Forecast Gabon", "Forecast Gabon"),
        ],
    )
    def test_these_are_the_same_name(self, left: str, right: str) -> None:
        assert normalise_name(left) == normalise_name(right)

    def test_these_are_not(self) -> None:
        assert normalise_name("Sylvie Mba") != normalise_name("Sylvie Mbo")

    def test_a_name_made_only_of_noise_words_still_produces_a_key(self) -> None:
        # Stripping every word would leave nothing to key on, and an empty key
        # would silently merge every such entity into one row.
        assert normalise_name("Le Projet") != ""


class TestResolutionKey:
    def test_a_person_named_twice_resolves_to_one_entity(self) -> None:
        assert resolution_key(EntityKind.PERSON, "Jean-Marc") == resolution_key(
            EntityKind.PERSON, "jean marc"
        )

    def test_the_same_name_under_two_kinds_stays_separate(self) -> None:
        # "Orange" the company and "Orange" the product are different things,
        # and merging them would produce nonsense in both views.
        assert resolution_key(EntityKind.COMPANY, "Orange") != resolution_key(
            EntityKind.PRODUCT, "Orange"
        )

    def test_two_identically_phrased_decisions_do_merge(self) -> None:
        assert resolution_key(EntityKind.DECISION, "Reporter le lancement") == resolution_key(
            EntityKind.DECISION, "reporter le lancement"
        )

    def test_two_differently_phrased_decisions_do_not(self) -> None:
        # Conservative on purpose: wrongly merging two decisions loses one
        # forever, wrongly splitting them merely shows two rows.
        assert resolution_key(EntityKind.DECISION, "Reporter le lancement au 3 mars") != (
            resolution_key(EntityKind.DECISION, "Reporter le lancement")
        )


class TestExtractedEntity:
    def test_the_verbatim_name_is_kept_for_display(self) -> None:
        entity = _entity(EntityKind.PERSON, "Jean-Marc Ondo")
        assert entity.name == "Jean-Marc Ondo"
        assert entity.normalised_name == "jean marc ondo"

    def test_surrounding_whitespace_is_tidied(self) -> None:
        assert _entity(EntityKind.COMPANY, "  Total   SA ").name == "Total SA"

    def test_an_empty_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntity(kind=EntityKind.PERSON, name="", confidence=0.9)

    def test_confidence_outside_zero_to_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntity(kind=EntityKind.PERSON, name="Paul", confidence=1.4)

    def test_unknown_fields_are_rejected(self) -> None:
        # Strict decoding means a model inventing a field is a failure, not a
        # silently ignored extra.
        with pytest.raises(ValidationError):
            ExtractedEntity.model_validate(
                {"kind": "person", "name": "Paul", "confidence": 0.9, "salary": 50000}
            )


class TestKnowledgeExtraction:
    def test_an_empty_extraction_is_valid(self) -> None:
        # Most captures name nothing. That has to be a normal result, not an
        # error path, or the worker spends its life retrying.
        extraction = KnowledgeExtraction()
        assert extraction.is_empty()

    def test_topics_are_deduplicated_and_trimmed(self) -> None:
        extraction = KnowledgeExtraction(topics=["  Forecast ", "Forecast", "Logistique"])
        assert extraction.topics == ["Forecast", "Logistique"]

    def test_repeats_within_one_capture_collapse_to_one(self) -> None:
        extraction = KnowledgeExtraction(
            entities=[
                _entity(EntityKind.PERSON, "Sylvie", 0.6),
                _entity(EntityKind.PERSON, "sylvie", 0.95),
                _entity(EntityKind.COMPANY, "Total", 0.9),
            ]
        )
        kept = extraction.deduplicated()
        assert len(kept) == 2

    def test_the_most_confident_phrasing_survives(self) -> None:
        extraction = KnowledgeExtraction(
            entities=[
                _entity(EntityKind.PERSON, "Sylvie", 0.6),
                _entity(EntityKind.PERSON, "Sylvie Mba", 0.95),
            ]
        )
        # Different names, so both survive — but within one key the best wins.
        by_key = KnowledgeExtraction(
            entities=[
                _entity(EntityKind.PERSON, "sylvie mba", 0.6),
                _entity(EntityKind.PERSON, "Sylvie Mba", 0.95),
            ]
        ).deduplicated()
        assert len(extraction.deduplicated()) == 2
        assert [item.name for item in by_key] == ["Sylvie Mba"]

    def test_low_confidence_entities_are_discarded(self) -> None:
        extraction = KnowledgeExtraction(
            entities=[_entity(EntityKind.PERSON, "Peut-être Paul", 0.2)]
        )
        assert extraction.deduplicated() == []


class TestSchema:
    def test_every_object_is_strict(self) -> None:
        # Providers reject a strict schema that omits this, and a non-strict
        # schema is how invented fields get through.
        schema = json_schema_for_llm()
        assert schema["additionalProperties"] is False
        for definition in schema.get("$defs", {}).values():
            if definition.get("type") == "object":
                assert definition["additionalProperties"] is False

    def test_every_property_is_required(self) -> None:
        schema = json_schema_for_llm()
        assert set(schema["required"]) == set(schema["properties"])
