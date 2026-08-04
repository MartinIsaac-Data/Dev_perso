"""The prompt registry, and the one safety property that must hold for all of it.

`test_every_prompt_handling_user_content_says_so` is the reason the registry
exists. Prompt injection through a *capture* is not hypothetical here: the
product's entire input is dictated or pasted text, and someone reading a
document aloud will eventually read out something shaped like an instruction.
Each prompt defends against that individually; only a registry lets a test
assert that none of them forgot.

The fingerprint tests protect history. `ai_run.prompt_fingerprint` points at
exact text; if the phase 1 prompt's hash changes, every stored run row now
references text that no longer exists anywhere.
"""

from __future__ import annotations

import pytest

from app.prompts import all_prompts, extraction, fingerprints, get, registry
from app.prompts.digest import DigestPeriod, for_period
from app.prompts.registry import INJECTION_GUARD_MARKER, Prompt


class TestRegistry:
    def test_every_prompt_the_phase_requires_is_registered(self) -> None:
        names = {prompt.name for prompt in all_prompts()}
        assert names == {
            "answer_with_context",
            "digest_daily",
            "digest_monthly",
            "digest_weekly",
            "extract_entities",
            "extract_memory",
            "extract_note_analysis",
            "meeting_live",
            "meeting_summary",
            "narrate_themes",
        }

    def test_lookup_by_name(self) -> None:
        assert get("extract_entities").name == "extract_entities"

    def test_an_unknown_name_names_what_is_available(self) -> None:
        with pytest.raises(KeyError, match="extract_note_analysis"):
            get("does_not_exist")

    def test_registering_a_duplicate_name_is_refused(self) -> None:
        # A silently overwritten prompt shows up as "the summaries got worse
        # last Tuesday" and takes a day to find.
        with pytest.raises(ValueError, match="already registered"):
            registry.register(Prompt(name="extract_entities", version=1, system="x"))

    def test_the_reference_is_readable_in_a_log(self) -> None:
        assert get("extract_entities").reference == "extract_entities@1"


class TestSafety:
    @pytest.mark.parametrize("prompt", all_prompts(), ids=lambda prompt: prompt.name)
    def test_every_prompt_handling_user_content_says_so(self, prompt: Prompt) -> None:
        if not prompt.handles_user_content:
            pytest.skip("declared as never seeing user text")
        assert prompt.has_injection_guard, (
            f"{prompt.name} interpolates user content but never states that the "
            f"content is data — expected the marker {INJECTION_GUARD_MARKER!r}"
        )

    @pytest.mark.parametrize("prompt", all_prompts(), ids=lambda prompt: prompt.name)
    def test_every_prompt_is_substantial(self, prompt: Prompt) -> None:
        # A truncated prompt still runs and still returns fluent output; the
        # only symptom is that the answers get worse.
        assert len(prompt.system) > 200

    @pytest.mark.parametrize("prompt", all_prompts(), ids=lambda prompt: prompt.name)
    def test_no_prompt_carries_an_unfilled_placeholder(self, prompt: Prompt) -> None:
        assert "{" not in prompt.system


class TestFingerprints:
    def test_a_fingerprint_is_stable(self) -> None:
        assert get("extract_entities").fingerprint == get("extract_entities").fingerprint

    def test_the_phase_one_prompt_still_hashes_as_it_did(self) -> None:
        # Moving the text into app/prompts must not orphan the ai_run rows that
        # already point at this hash.
        assert extraction.prompt_fingerprint() == extraction.EXTRACTION_PROMPT.fingerprint

    def test_different_text_hashes_differently(self) -> None:
        assert Prompt(name="a", version=1, system="x").fingerprint != (
            Prompt(name="b", version=1, system="y").fingerprint
        )

    def test_the_map_covers_every_prompt(self) -> None:
        assert set(fingerprints()) == {prompt.name for prompt in all_prompts()}


class TestBackwardCompatibility:
    def test_the_old_import_path_still_works(self) -> None:
        # Phase 1 and 2 code imports from here. "Ne jamais casser l'existant".
        from app.infra.ai import prompts as legacy

        assert legacy.SYSTEM_PROMPT == extraction.SYSTEM_PROMPT
        assert legacy.PROMPT_NAME == "extract_note_analysis"
        assert legacy.prompt_fingerprint() == extraction.prompt_fingerprint()

    def test_the_context_builders_are_unchanged(self) -> None:
        from app.infra.ai import prompts as legacy

        assert legacy.build_context_block is extraction.build_context_block
        assert legacy.build_transcript_block is extraction.build_transcript_block


class TestDigests:
    @pytest.mark.parametrize("period", list(DigestPeriod))
    def test_each_period_has_its_own_prompt(self, period: DigestPeriod) -> None:
        assert for_period(period).name == f"digest_{period.value}"

    def test_the_three_periods_ask_for_different_things(self) -> None:
        # One prompt with a variable period produces three mediocre summaries.
        systems = {for_period(period).system for period in DigestPeriod}
        assert len(systems) == 3

    def test_the_daily_digest_is_the_shortest_brief(self) -> None:
        assert "120 mots" in for_period(DigestPeriod.DAILY).system
        assert "350 mots" in for_period(DigestPeriod.MONTHLY).system


class TestRendering:
    def test_retrieved_passages_are_numbered_from_one(self) -> None:
        from app.prompts.answer import build_context_block

        block = build_context_block([("Réunion du 3 mars", "On a parlé du forecast.")])
        assert "[1] Réunion du 3 mars" in block
        assert "<extraits>" in block

    def test_an_empty_retrieval_says_so_instead_of_rendering_nothing(self) -> None:
        # An empty <extraits> block invites the model to fill the silence.
        from app.prompts.answer import NO_CONTEXT_NOTICE, build_context_block

        assert build_context_block([]) == NO_CONTEXT_NOTICE

    def test_entity_extraction_wraps_content_in_a_delimiter(self) -> None:
        from app.prompts.entities import build_user_block

        block = build_user_block("Vu Sylvie ce matin.", title="Note", occurred_at="2026-03-03")
        assert "<contenu>" in block and "</contenu>" in block
        assert block.index("Titre : Note") < block.index("<contenu>")

    def test_digest_counts_are_given_as_facts_not_left_to_be_tallied(self) -> None:
        from app.prompts.digest import build_material_block

        block = build_material_block(
            "Semaine du 1er juin", ["Réunion forecast"], stats=["14 tâches terminées"]
        )
        assert "Chiffres (exacts, calculés)" in block
        assert "14 tâches terminées" in block

    def test_an_empty_period_renders_explicitly(self) -> None:
        from app.prompts.digest import build_material_block

        assert "(aucun élément sur la période)" in build_material_block("Hier", [])

    def test_theme_counts_are_grouped_by_kind(self) -> None:
        from app.prompts.insights import build_counts_block

        block = build_counts_block(
            "Mai 2026",
            [
                ("Projet", "Forecast Gabon", 23),
                ("Personne", "Sylvie Mba", 19),
                ("Projet", "Refonte", 4),
            ],
        )
        assert block.count("Projet") == 1
        assert "23 mentions" in block
        assert "<comptages>" in block

    def test_a_single_mention_is_singular(self) -> None:
        from app.prompts.insights import build_counts_block

        assert "1 mention\n" in build_counts_block("Mai", [("Projet", "X", 1)]) + "\n"

    def test_known_memories_are_listed_so_they_are_not_proposed_again(self) -> None:
        from app.prompts.memory import build_known_block

        assert build_known_block([]) == "Aucune mémoire existante."
        assert "- Je dirige le pôle forecast" in build_known_block(["Je dirige le pôle forecast"])

    def test_conversation_turns_are_labelled_in_french(self) -> None:
        from app.prompts.memory import build_conversation_block

        block = build_conversation_block([("user", "Bonjour"), ("assistant", "Bonjour")])
        assert "Utilisateur : Bonjour" in block
        assert "Assistant : Bonjour" in block
