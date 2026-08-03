"""Intent routing, starting with the five questions the product must answer.

`TestTheFiveRequiredQuestions` is the acceptance test for phase 3's headline
requirement. Each of the five is asserted here at the routing level and again
end-to-end in `tests/integration/test_assistant.py` — this file proves the right
handler is chosen, that one proves the handler returns the right thing.

The rest of the file is about the ways real input differs from the examples:
accents dropped by a phone keyboard, no question mark, extra politeness.
"""

from __future__ import annotations

import pytest

from app.domain.intent import Intent, classify, plan


class TestTheFiveRequiredQuestions:
    def test_que_dois_je_faire_aujourdhui(self) -> None:
        result = classify("Que dois-je faire aujourd'hui ?")
        assert result.intent is Intent.TODAY
        assert result.is_confident
        # No model: the agenda knows this exactly, and a model can only
        # approximate it more slowly and for money.
        assert not result.intent.needs_generation

    def test_resume_mes_reunions(self) -> None:
        result = classify("Résume mes réunions.")
        assert result.intent is Intent.SUMMARISE
        assert result.entry_type == "meeting"
        assert result.intent.needs_retrieval

    def test_montre_les_notes_concernant_le_forecast_gabon(self) -> None:
        result = classify("Montre les notes concernant le Forecast Gabon")
        assert result.intent is Intent.RECALL
        # The verb and its connectives are stripped; what is left is what to
        # search for.
        assert result.subject == "forecast gabon"

    def test_quels_sujets_reviennent_souvent(self) -> None:
        result = classify("Quels sujets reviennent souvent ?")
        assert result.intent is Intent.THEMES

    def test_quelles_sont_mes_taches_en_retard(self) -> None:
        result = classify("Quelles sont mes tâches en retard ?")
        assert result.intent is Intent.OVERDUE
        assert not result.intent.needs_generation


class TestRobustness:
    @pytest.mark.parametrize(
        "question",
        [
            "Que dois-je faire aujourd'hui ?",
            "que dois je faire aujourd hui",
            "QUE DOIS-JE FAIRE AUJOURD'HUI",
            "Bon, que dois-je faire aujourd'hui du coup",
        ],
    )
    def test_case_accents_and_politeness_do_not_change_the_route(self, question: str) -> None:
        assert classify(question).intent is Intent.TODAY

    @pytest.mark.parametrize(
        "question",
        ["Résume mes réunions", "resume mes reunions", "Fais une synthèse de mes réunions"],
    )
    def test_meeting_summaries_survive_rephrasing(self, question: str) -> None:
        result = classify(question)
        assert result.intent is Intent.SUMMARISE
        assert result.entry_type == "meeting"

    def test_an_empty_question_does_not_raise(self) -> None:
        result = classify("   ")
        assert result.intent is Intent.OPEN_QUESTION
        assert result.confidence == 0.0


class TestOrdering:
    def test_a_specific_rule_wins_over_a_general_one(self) -> None:
        # "résume" alone is a generic summary; "résume mes réunions" is not, and
        # the generic rule must not swallow it.
        assert classify("Résume ma semaine").entry_type is None
        assert classify("Résume mes réunions").entry_type == "meeting"

    def test_overdue_wins_over_today(self) -> None:
        # "qu'ai-je en retard aujourd'hui" is a question about lateness. Routing
        # it to the agenda would answer a different question convincingly.
        assert classify("Qu'est-ce que j'ai en retard aujourd'hui ?").intent is Intent.OVERDUE

    def test_a_bare_verb_with_no_subject_is_not_a_recall(self) -> None:
        # "montre" alone names nothing to search for; falling through to RAG is
        # the honest handling.
        assert classify("Montre").intent is Intent.OPEN_QUESTION


class TestFallback:
    def test_an_unmatched_question_goes_to_rag(self) -> None:
        result = classify("Pourquoi le fournisseur a-t-il changé ses conditions ?")
        assert result.intent is Intent.OPEN_QUESTION
        assert result.intent.needs_retrieval
        assert result.intent.needs_generation

    def test_low_confidence_means_no_shortcut_not_incomprehension(self) -> None:
        result = classify("Pourquoi le fournisseur a-t-il changé ses conditions ?")
        assert 0 < result.confidence < 0.7
        # The whole question is kept as the search subject.
        assert result.subject == "Pourquoi le fournisseur a-t-il changé ses conditions ?"


class TestPlan:
    def test_a_structured_question_plans_no_model_call(self) -> None:
        made = plan("Quelles sont mes tâches en retard ?")
        assert made.intent is Intent.OVERDUE
        assert not made.use_generation
        assert not made.use_retrieval

    def test_a_meeting_summary_narrows_the_search_to_meetings(self) -> None:
        made = plan("Résume mes réunions")
        assert made.entry_types == ("meeting",)
        assert made.use_retrieval and made.use_generation

    def test_the_search_query_drops_the_verb(self) -> None:
        made = plan("Montre les notes concernant le Forecast Gabon")
        assert made.search_query == "forecast gabon"

    def test_an_upcoming_question_carries_its_window(self) -> None:
        made = plan("Qu'est-ce qui m'attend cette semaine ?")
        assert made.intent is Intent.UPCOMING
        assert made.window_days == 7

    def test_the_plan_is_explainable_to_the_user(self) -> None:
        # An assistant that can say how it answered is one a user can correct.
        made = plan("Que dois-je faire aujourd'hui ?")
        assert made.notes
        assert "sans modèle de langage" in made.notes[0]

    def test_an_open_question_searches_on_the_question_itself(self) -> None:
        made = plan("Où en est la négociation avec le fournisseur ?")
        assert made.use_retrieval
        assert "négociation" in made.search_query
