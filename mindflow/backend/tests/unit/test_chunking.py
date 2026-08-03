"""Chunking: the properties that decide whether retrieval works at all.

Three of these tests protect money rather than correctness. Chunking that is not
deterministic re-embeds the whole corpus on every pass, and the bill for that
arrives before anyone notices the duplicates.
"""

from __future__ import annotations

from app.domain import chunking
from app.domain.chunking import MAX_CHARS, MIN_CHARS, Chunk, content_hash, split


def _paragraph(sentences: int, *, word: str = "reunion") -> str:
    return " ".join(
        f"Nous avons parle du {word} numero {index} avec toute l'equipe du projet."
        for index in range(sentences)
    )


class TestNormalise:
    def test_collapses_runs_of_spaces_without_touching_words(self) -> None:
        assert chunking.normalise("Bonjour    le   monde") == "Bonjour le monde"

    def test_trims_each_line_and_the_whole(self) -> None:
        assert chunking.normalise("  a  \n   b  \n") == "a\nb"

    def test_composed_and_decomposed_accents_normalise_alike(self) -> None:
        # "é" as one code point, then as "e" + combining acute. Two platforms,
        # one sentence — they must not become two rows in the index.
        assert chunking.normalise("réunion") == chunking.normalise("réunion")


class TestContentHash:
    def test_is_stable_across_calls(self) -> None:
        assert content_hash("Rappeler le DAF") == content_hash("Rappeler le DAF")

    def test_ignores_whitespace_only_edits(self) -> None:
        # This is what makes re-indexing after a formatting change free.
        assert content_hash("Rappeler  le DAF ") == content_hash("Rappeler le DAF")

    def test_changes_when_a_word_changes(self) -> None:
        assert content_hash("Rappeler le DAF") != content_hash("Rappeler la DAF")

    def test_is_short_enough_to_index(self) -> None:
        assert len(content_hash("x")) == 32


class TestSplit:
    def test_empty_text_yields_nothing(self) -> None:
        assert split("") == []
        assert split("   \n  ") == []

    def test_a_short_note_stays_whole(self) -> None:
        # Cutting a two-sentence voice note in half makes both halves retrieve
        # worse than the whole did.
        chunks = split("Rappeler le DAF. C'est urgent.")
        assert len(chunks) == 1
        assert chunks[0].text == "Rappeler le DAF. C'est urgent."
        assert chunks[0].index == 0

    def test_a_long_text_is_split(self) -> None:
        chunks = split(_paragraph(60))
        assert len(chunks) > 1

    def test_every_chunk_stays_under_the_ceiling(self) -> None:
        for chunk in split(_paragraph(200)):
            assert len(chunk.text) <= MAX_CHARS

    def test_indexes_are_contiguous_from_zero(self) -> None:
        chunks = split(_paragraph(120))
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))

    def test_chunks_overlap_so_a_pronoun_keeps_its_antecedent(self) -> None:
        chunks = split(_paragraph(60))
        assert len(chunks) > 1
        # The tail of one chunk reappears at the head of the next.
        first_words = chunks[1].text.split()[:6]
        assert " ".join(first_words) in chunks[0].text

    def test_no_chunk_is_a_stub(self) -> None:
        # A trailing fragment is merged rather than emitted: a five-word chunk
        # retrieves noise and dilutes whatever it is averaged with.
        chunks = split(_paragraph(41))
        assert len(chunks) > 1
        assert all(len(chunk.text) >= MIN_CHARS for chunk in chunks)

    def test_is_deterministic(self) -> None:
        text = _paragraph(90)
        first = split(text)
        second = split(text)
        assert [chunk.content_hash for chunk in first] == [chunk.content_hash for chunk in second]

    def test_a_monologue_with_no_full_stop_is_still_split(self) -> None:
        # Spoken French produces this constantly: three minutes, no punctuation.
        monologue = "alors " * 900
        chunks = split(monologue)
        assert len(chunks) > 1
        assert all(len(chunk.text) <= MAX_CHARS for chunk in chunks)

    def test_no_content_is_dropped(self) -> None:
        text = _paragraph(80, word="forecast")
        joined = " ".join(chunk.text for chunk in split(text))
        assert "numero 0 " in joined
        assert "numero 79" in joined

    def test_hashes_identify_the_text_not_the_position(self) -> None:
        chunk = Chunk(text="Rappeler le DAF", index=3, start_char=10, end_char=25, content_hash="x")
        assert content_hash(chunk.text) == content_hash("Rappeler le DAF")


class TestBudget:
    def test_estimates_tokens_from_characters(self) -> None:
        assert chunking.estimate_tokens("a" * 360) == 100

    def test_never_estimates_zero(self) -> None:
        # A zero-cost passage would slip past every budget check.
        assert chunking.estimate_tokens("a") == 1

    def test_takes_pieces_in_order_until_the_budget_runs_out(self) -> None:
        pieces = ["a" * 360, "b" * 360, "c" * 360]
        kept = chunking.fit_to_budget(pieces, budget_tokens=150)
        assert kept[0] == pieces[0]
        assert len(kept) == 2

    def test_truncates_the_last_piece_rather_than_dropping_it(self) -> None:
        kept = chunking.fit_to_budget(["a" * 360, "b" * 3600], budget_tokens=200)
        assert len(kept) == 2
        assert kept[1].endswith("[…]")
        assert len(kept[1]) < 3600

    def test_drops_a_remainder_too_small_to_be_useful(self) -> None:
        kept = chunking.fit_to_budget(["a" * 360, "b" * 3600], budget_tokens=110)
        assert len(kept) == 1

    def test_an_empty_list_is_not_an_error(self) -> None:
        assert chunking.fit_to_budget([], budget_tokens=1000) == []
