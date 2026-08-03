"""Reciprocal rank fusion, and the properties that make hybrid search worth it.

The test that matters most is `test_consensus_beats_a_single_first_place`: it is
the entire reason RRF was chosen over score normalisation, and if it ever fails
the hybrid retriever has silently become "whichever retriever shouts loudest".
"""

from __future__ import annotations

from app.domain.retrieval import (
    RRF_K,
    Candidate,
    Citation,
    Retriever,
    attach_scores,
    deduplicate_citations,
    reciprocal_rank_fusion,
)


class TestFusion:
    def test_a_single_ranking_is_returned_in_order(self) -> None:
        fused = reciprocal_rank_fusion({Retriever.LEXICAL: ["a", "b", "c"]})
        assert [item.ref for item in fused] == ["a", "b", "c"]

    def test_an_empty_ranking_is_not_an_error(self) -> None:
        # A semantic search with no index yet is exactly this. The lexical
        # ranking alone remains a perfectly good answer.
        fused = reciprocal_rank_fusion(
            {Retriever.LEXICAL: ["a", "b"], Retriever.SEMANTIC: []},
        )
        assert [item.ref for item in fused] == ["a", "b"]

    def test_everything_empty_yields_nothing(self) -> None:
        assert reciprocal_rank_fusion({Retriever.LEXICAL: [], Retriever.SEMANTIC: []}) == []

    def test_consensus_beats_a_single_first_place(self) -> None:
        # "b" is second on both lists; "a" is first on one and absent from the
        # other. Agreement wins — this is the whole point of the fusion.
        fused = reciprocal_rank_fusion(
            {
                Retriever.LEXICAL: ["a", "b", "c"],
                Retriever.SEMANTIC: ["z", "b", "y"],
            }
        )
        assert fused[0].ref == "b"
        assert fused[0].is_consensus

    def test_scores_use_the_documented_formula(self) -> None:
        fused = reciprocal_rank_fusion({Retriever.LEXICAL: ["a"]})
        assert fused[0].fused == 1.0 / (RRF_K + 1)

    def test_a_duplicate_within_one_ranking_is_counted_once(self) -> None:
        # A retriever returning the same chunk twice must not double its weight.
        fused = reciprocal_rank_fusion({Retriever.LEXICAL: ["a", "a", "b"]})
        assert fused[0].ranks == {Retriever.LEXICAL: 1}
        assert fused[0].fused == 1.0 / (RRF_K + 1)

    def test_weights_can_silence_a_retriever(self) -> None:
        fused = reciprocal_rank_fusion(
            {Retriever.LEXICAL: ["a"], Retriever.SEMANTIC: ["b"]},
            weights={Retriever.LEXICAL: 1.0, Retriever.SEMANTIC: 0.0},
        )
        assert [item.ref for item in fused] == ["a"]

    def test_weights_tilt_the_ranking(self) -> None:
        fused = reciprocal_rank_fusion(
            {Retriever.LEXICAL: ["a"], Retriever.SEMANTIC: ["b"]},
            weights={Retriever.LEXICAL: 1.0, Retriever.SEMANTIC: 3.0},
        )
        assert fused[0].ref == "b"

    def test_the_order_is_stable_for_equal_scores(self) -> None:
        # An unstable order means the same query returns results in a different
        # order on every call, which reads as a broken cache.
        first = reciprocal_rank_fusion({Retriever.LEXICAL: ["b"], Retriever.SEMANTIC: ["a"]})
        second = reciprocal_rank_fusion({Retriever.SEMANTIC: ["a"], Retriever.LEXICAL: ["b"]})
        assert [item.ref for item in first] == [item.ref for item in second]

    def test_the_limit_truncates_after_ranking_not_before(self) -> None:
        # "b" is second on both lists and would be cut by a naive
        # truncate-then-fuse; it must survive as the consensus winner.
        fused = reciprocal_rank_fusion(
            {
                Retriever.LEXICAL: ["a", "b", "c"],
                Retriever.SEMANTIC: ["z", "b", "y"],
            },
            limit=2,
        )
        assert [item.ref for item in fused] == ["b", "a"]

    def test_mirrored_rankings_favour_the_extremes(self) -> None:
        # A document ranked first by one retriever and last by the other beats
        # one ranked middling by both. That is RRF working as designed, not a
        # bug: 1/61 + 1/63 > 2/62, because the reciprocal curve is convex.
        fused = reciprocal_rank_fusion(
            {
                Retriever.LEXICAL: ["a", "b", "c"],
                Retriever.SEMANTIC: ["c", "b", "a"],
            }
        )
        assert fused[-1].ref == "b"

    def test_records_where_each_retriever_placed_an_item(self) -> None:
        fused = reciprocal_rank_fusion(
            {Retriever.LEXICAL: ["x", "a"], Retriever.SEMANTIC: ["a"]},
        )
        found = next(item for item in fused if item.ref == "a")
        assert found.ranks == {Retriever.LEXICAL: 2, Retriever.SEMANTIC: 1}
        assert found.found_by == (Retriever.LEXICAL, Retriever.SEMANTIC)

    def test_an_item_found_once_is_not_consensus(self) -> None:
        fused = reciprocal_rank_fusion({Retriever.LEXICAL: ["a"]})
        assert not fused[0].is_consensus


class TestAttachScores:
    def test_raw_scores_are_recorded_for_explanation(self) -> None:
        candidates = [Candidate(ref="a"), Candidate(ref="b")]
        attach_scores(candidates, Retriever.SEMANTIC, {"a": 0.82})
        assert candidates[0].scores == {Retriever.SEMANTIC: 0.82}
        assert candidates[1].scores == {}

    def test_raw_scores_never_change_the_ranking(self) -> None:
        # They are shown, not used. That is the whole premise of RRF.
        fused = reciprocal_rank_fusion({Retriever.LEXICAL: ["a", "b"]})
        before = [item.fused for item in fused]
        attach_scores(fused, Retriever.LEXICAL, {"b": 99.0})
        assert [item.fused for item in fused] == before


def _citation(ref: str, entry_id: str | None) -> Citation:
    return Citation(ref=ref, entry_id=entry_id, capture_id=None, title="t", excerpt="e")


class TestCitations:
    def test_three_chunks_of_one_meeting_cite_it_once(self) -> None:
        kept = deduplicate_citations(
            [_citation("c1", "e1"), _citation("c2", "e1"), _citation("c3", "e2")]
        )
        assert [item.ref for item in kept] == ["c1", "c3"]

    def test_the_first_occurrence_wins_so_the_best_ranked_survives(self) -> None:
        kept = deduplicate_citations([_citation("best", "e1"), _citation("worse", "e1")])
        assert kept[0].ref == "best"

    def test_falls_back_to_the_chunk_reference_when_nothing_else_identifies_it(self) -> None:
        kept = deduplicate_citations([_citation("c1", None), _citation("c2", None)])
        assert len(kept) == 2

    def test_the_list_is_capped(self) -> None:
        many = [_citation(f"c{index}", f"e{index}") for index in range(30)]
        assert len(deduplicate_citations(many, limit=8)) == 8

    def test_no_citations_is_not_an_error(self) -> None:
        assert deduplicate_citations([]) == []
