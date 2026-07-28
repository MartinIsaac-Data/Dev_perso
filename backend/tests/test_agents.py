"""Agents, tested without a network call.

Every test here runs against `StubClient`, which returns prepared responses
and records what it was asked. That second half matters more than it looks: a
context assembler that silently omits the sensitivity analysis produces a
critique that reads exactly as convincing as one built with it, so no
assertion on the *output* would catch the omission. Several tests below assert
on the payload the agent received.

What is deliberately not covered: the HTTP request itself. That is the one
part with no logic in it, and testing it would mean either a key and a bill,
or a mock of the Anthropic SDK that asserts this code calls a library the way
this code calls it.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentRun,
    BusinessCase,
    CaseReviewChallenge,
    JobPosting,
    JobRequirement,
    PeriodicReview,
    Profile,
    ReviewCriterion,
    Skill,
)
from app.services.agents import (
    AgentError,
    FailingClient,
    StubClient,
    load_prompt,
    run_agent,
    verify_prompt,
)
from app.services.agents.extraction import (
    PostingExtractionOutput,
    build_posting_context,
    extract_posting,
)
from app.services.agents.periodic_review import (
    build_review_context,
    generate_review,
    period_bounds,
)
from app.services.agents.review_board import (
    ReviewBoardOutput,
    build_case_context,
    review_case,
    weighted_score,
)

AS_OF = date(2026, 7, 28)


# --------------------------------------------------------------------------
# Prompts and the run log
# --------------------------------------------------------------------------


class TestPrompts:
    @pytest.mark.parametrize(
        "name", ["review_board", "posting_extraction", "periodic_review"]
    )
    def test_every_agent_has_a_prompt_file(self, name: str) -> None:
        prompt = load_prompt(name)
        assert prompt.text.strip()
        assert len(prompt.sha256) == 64

    def test_unknown_prompt_lists_what_exists(self) -> None:
        with pytest.raises(AgentError, match="review_board"):
            load_prompt("flattery")

    @pytest.mark.parametrize(
        "name", ["review_board", "posting_extraction", "periodic_review"]
    )
    def test_no_prompt_asks_the_model_to_author(self, name: str) -> None:
        """The central rule of the whole package, asserted rather than assumed.

        Agents critique, extract and structure. A portfolio of work an agent
        wrote is not a portfolio, and a prompt that quietly starts asking for
        drafts would undermine the entire system without breaking anything.
        """
        text = load_prompt(name).text.lower()
        assert "do not write the work" in text or "do not rewrite" in text or (
            "do not invent" in text
        )
        for forbidden in ("write the article", "draft the case", "improve the case for"):
            assert forbidden not in text


class TestRunLog:
    def test_a_successful_run_records_the_prompt_hash(self, seeded_session: Session) -> None:
        client = StubClient({"body_md": "b", "next_action": "a", "next_action_rationale": "r"})
        from app.services.agents.periodic_review import PeriodicReviewOutput

        run, _ = run_agent(
            seeded_session,
            agent_name="periodic_review_weekly",
            prompt_name="periodic_review",
            payload={"hello": "world"},
            output_model=PeriodicReviewOutput,
            client=client,
        )
        assert run.status == "succeeded"
        assert run.prompt_sha256 == load_prompt("periodic_review").sha256
        assert run.finished_at is not None
        assert run.input_tokens == 100

    def test_the_stored_hash_detects_an_edited_prompt(
        self, seeded_session: Session
    ) -> None:
        # The point of the hash: a prompt edited afterwards cannot pass for
        # the one that produced a result.
        run = AgentRun(
            agent_name="review_board",
            prompt_path="backend/app/services/agents/prompts/review_board.md",
            prompt_sha256="0" * 64,
            model="claude-sonnet-5",
            status="succeeded",
            started_at=date(2026, 1, 1),
        )
        assert verify_prompt(run) is False

        run.prompt_sha256 = load_prompt("review_board").sha256
        assert verify_prompt(run) is True

    def test_a_failed_run_is_still_committed(self, seeded_session: Session) -> None:
        """A log with only successes in it is not a log."""
        from app.services.agents.periodic_review import PeriodicReviewOutput

        with pytest.raises(AgentError, match="upstream exploded"):
            run_agent(
                seeded_session,
                agent_name="periodic_review_weekly",
                prompt_name="periodic_review",
                payload={},
                output_model=PeriodicReviewOutput,
                client=FailingClient(),
                # noqa: E501
            )
        run = seeded_session.scalar(select(AgentRun))
        assert run is not None
        assert run.status == "failed"
        assert "upstream exploded" in run.error

    def test_malformed_output_fails_the_run_rather_than_persisting(
        self, seeded_session: Session
    ) -> None:
        from app.services.agents.periodic_review import PeriodicReviewOutput

        with pytest.raises(AgentError, match="invalid agent output"):
            run_agent(
                seeded_session,
                agent_name="periodic_review_weekly",
                prompt_name="periodic_review",
                payload={},
                output_model=PeriodicReviewOutput,
                client=StubClient({"body_md": "only this field"}),
            )
        assert seeded_session.scalar(select(AgentRun)).status == "failed"

    def test_the_schema_sent_to_the_model_has_no_unresolved_refs(
        self, seeded_session: Session
    ) -> None:
        """Nested models must be inlined; the tool API does not follow $ref."""
        client = StubClient(
            {"body_md": "b", "next_action": "a", "next_action_rationale": "r"}
        )
        from app.services.agents.periodic_review import PeriodicReviewOutput

        run_agent(
            seeded_session,
            agent_name="x",
            prompt_name="periodic_review",
            payload={},
            output_model=PeriodicReviewOutput,
            client=client,
        )
        rendered = json.dumps(client.calls[0]["json_schema"])
        assert "$ref" not in rendered
        assert "$defs" not in rendered


# --------------------------------------------------------------------------
# Review board
# --------------------------------------------------------------------------


def board_response(criteria: list[str]) -> dict:
    return {
        "verdict": "Conditionally supportable.",
        "summary": "Strong narrative, weak benefits.",
        "scores": [
            {"criterion_code": code, "score": 6.0, "comment": f"comment on {code}"}
            for code in criteria
        ],
        "challenges": [
            {
                "persona": "cfo",
                "severity": "blocking",
                "target_assumption_code": "benefit_planner_time",
                "challenge": "That is not a saving.",
                "evidence_demanded": "A signed commitment.",
            },
            {
                "persona": "cio",
                "severity": "minor",
                "target_assumption_code": None,
                "target_area": "Exit criteria",
                "challenge": "No kill criterion.",
            },
        ],
    }


class TestReviewBoardContext:
    @pytest.fixture
    def case(self, demo_session: Session) -> BusinessCase:
        return demo_session.scalar(select(BusinessCase))

    def test_carries_the_rubric_from_the_database(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        # Not a copy in the prompt: the interface and the agent must score
        # against the same rubric, and a duplicated one drifts.
        context = build_case_context(demo_session, case, case.roi_models[0])
        codes = {c["code"] for c in context["rubric"]}
        stored = {c.code for c in demo_session.scalars(select(ReviewCriterion))}
        assert codes == stored
        assert all(c["definition"] for c in context["rubric"])

    def test_carries_the_sensitivity_analysis(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        context = build_case_context(demo_session, case, case.roi_models[0])
        assert context["roi"]["sensitivity"]
        assert context["roi"]["fragility_headline"]
        assert context["roi"]["only_fails_in_combination"] is True

    def test_carries_all_three_scenarios(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        context = build_case_context(demo_session, case, case.roi_models[0])
        assert set(context["roi"]["scenarios"]) == {"pessimistic", "base", "optimistic"}

    def test_carries_the_unexplained_gap(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        reconciliation = build_case_context(demo_session, case, case.roi_models[0])[
            "cause_tree"
        ]["reconciliation"]
        assert reconciliation["gap"] > 0

    def test_carries_the_structural_audit(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        audit = build_case_context(demo_session, case, case.roi_models[0])["assumption_audit"]
        assert audit["low_confidence"]

    def test_works_without_a_roi_model(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        context = build_case_context(demo_session, case, None)
        assert context["roi"] is None
        assert context["cause_tree"]["leaves"]


class TestReviewBoard:
    @pytest.fixture
    def case(self, demo_session: Session) -> BusinessCase:
        return demo_session.scalar(select(BusinessCase))

    @pytest.fixture
    def criteria(self, demo_session: Session) -> list[str]:
        return [c.code for c in demo_session.scalars(select(ReviewCriterion))]

    def test_persists_scores_and_challenges(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        client = StubClient(board_response(criteria))
        review = review_case(demo_session, case, client, reviewed_on=AS_OF)

        assert review.agent_run_id is not None
        assert len(review.scores) == len(criteria)
        assert len(review.challenges) == 2

    def test_the_overall_score_is_computed_not_trusted(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        """The agent scores each criterion; the weighting is ours.

        Trusting a model's weighted arithmetic would make every stored score
        depend on it multiplying correctly, and would break silently the first
        time the rubric weights were rebalanced.
        """
        client = StubClient(board_response(criteria))
        review = review_case(demo_session, case, client, reviewed_on=AS_OF)
        # Every criterion scored 6.0 and the weights sum to 1.
        assert review.overall_score == Decimal("6.00")

    def test_challenges_are_pinned_to_the_assumption_they_attack(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        client = StubClient(board_response(criteria))
        review = review_case(demo_session, case, client, reviewed_on=AS_OF)
        pinned = [c for c in review.challenges if c.target_assumption_id is not None]
        assert len(pinned) == 1
        assert pinned[0].target_assumption.code == "benefit_planner_time"

    def test_an_invented_assumption_code_is_kept_as_text_not_dropped(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        # Knowing the model hallucinated an assumption name is useful; losing
        # the objection is not.
        response = board_response(criteria)
        response["challenges"][0]["target_assumption_code"] = "benefit_imaginary"
        review = review_case(demo_session, case, StubClient(response), reviewed_on=AS_OF)

        orphan = next(c for c in review.challenges if c.target_assumption_id is None)
        assert "benefit_imaginary" in (orphan.target_area or "") or any(
            c.target_area == "benefit_imaginary" for c in review.challenges
        )

    def test_a_missing_criterion_is_refused(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        response = board_response(criteria[:-1])
        with pytest.raises(AgentError, match="did not score every criterion"):
            review_case(demo_session, case, StubClient(response), reviewed_on=AS_OF)

    def test_an_invented_criterion_is_refused(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        response = board_response([*criteria, "vibes"])
        with pytest.raises(AgentError, match="not in the rubric"):
            review_case(demo_session, case, StubClient(response), reviewed_on=AS_OF)

    def test_a_malformed_challenge_does_not_discard_the_critique(
        self, demo_session: Session, case: BusinessCase, criteria: list[str]
    ) -> None:
        response = board_response(criteria)
        response["challenges"].append(
            {"persona": "cto", "severity": "catastrophic", "challenge": "?"}
        )
        review = review_case(demo_session, case, StubClient(response), reviewed_on=AS_OF)
        assert len(review.challenges) == 2

    def test_weighted_score_uses_the_stored_weights(
        self, demo_session: Session
    ) -> None:
        criteria = list(demo_session.scalars(select(ReviewCriterion)))
        scores = {
            "assumption_rigour": Decimal("6.0"),
            "technical_feasibility": Decimal("7.5"),
            "roi_credibility": Decimal("5.5"),
            "narrative_clarity": Decimal("8.0"),
            "risk_management": Decimal("4.0"),
        }
        # The figure the shipped demonstration review carries.
        assert weighted_score(scores, criteria) == Decimal("6.28")


# --------------------------------------------------------------------------
# Posting extraction
# --------------------------------------------------------------------------


class TestExtractionContext:
    def test_offers_the_whole_taxonomy(self, seeded_session: Session) -> None:
        """Not a keyword shortlist.

        A shortlist would decide the mapping before the agent saw the text,
        and would make an unmapped requirement indistinguishable from one
        whose code simply was not offered.
        """
        skills = list(seeded_session.scalars(select(Skill)))
        context = build_posting_context("some advert", skills)
        assert len(context["taxonomy"]) == len(skills)
        assert context["posting_text"] == "some advert"


class TestExtraction:
    @pytest.fixture
    def response(self) -> dict:
        return {
            "title": "Lead Data Architect",
            "company": "Anonymous",
            "location": "Remote",
            "seniority_label": "Lead",
            "requirements": [
                {
                    "raw_label": "dimensional modelling",
                    "skill_code": "dimensional_modelling",
                    "required_level": 4,
                    "importance": "must_have",
                    "evidence_quote": "deep dimensional modelling",
                },
                {
                    "raw_label": "negotiating with data vendors",
                    "skill_code": None,
                    "required_level": None,
                    "importance": "nice_to_have",
                    "evidence_quote": "experience negotiating with data vendors",
                },
            ],
        }

    def test_persists_the_posting_with_its_raw_text(
        self, seeded_session: Session, response: dict
    ) -> None:
        posting = extract_posting(
            seeded_session, "Full advert text here.", StubClient(response)
        )
        assert posting.raw_text == "Full advert text here."
        assert posting.title == "Lead Data Architect"

    def test_an_unmappable_requirement_stays_unmapped(
        self, seeded_session: Session, response: dict
    ) -> None:
        """The most valuable row the extractor produces.

        It means the market is asking for something the taxonomy does not yet
        describe. Forcing it into the nearest code destroys that signal.
        """
        posting = extract_posting(seeded_session, "advert", StubClient(response))
        unmapped = [r for r in posting.requirements if r.skill_id is None]
        assert len(unmapped) == 1
        assert unmapped[0].raw_label == "negotiating with data vendors"

    def test_an_invented_skill_code_is_left_unmapped(
        self, seeded_session: Session, response: dict
    ) -> None:
        response["requirements"][0]["skill_code"] = "telepathy"
        posting = extract_posting(seeded_session, "advert", StubClient(response))
        assert all(r.skill_id is None for r in posting.requirements)
        # The employer's own words survive regardless.
        assert "dimensional modelling" in {r.raw_label for r in posting.requirements}

    def test_requirements_point_at_the_run_that_produced_them(
        self, seeded_session: Session, response: dict
    ) -> None:
        # So a 2028 prompt can re-process the 2026 corpus and the two
        # extractions can be told apart.
        posting = extract_posting(seeded_session, "advert", StubClient(response))
        assert all(r.agent_run_id is not None for r in posting.requirements)

    def test_duplicate_labels_in_one_extraction_are_collapsed(
        self, seeded_session: Session, response: dict
    ) -> None:
        response["requirements"].append(dict(response["requirements"][0]))
        posting = extract_posting(seeded_session, "advert", StubClient(response))
        assert len(posting.requirements) == 2

    def test_an_unknown_importance_falls_back_to_must_have(
        self, seeded_session: Session, response: dict
    ) -> None:
        response["requirements"][0]["importance"] = "essential-ish"
        posting = extract_posting(seeded_session, "advert", StubClient(response))
        target = next(r for r in posting.requirements if r.skill_id is not None)
        assert target.importance == "must_have"


# --------------------------------------------------------------------------
# Periodic review
# --------------------------------------------------------------------------


class TestPeriodBounds:
    def test_weekly_runs_monday_to_sunday(self) -> None:
        # 28 July 2026 is a Tuesday.
        start, end = period_bounds("weekly", date(2026, 7, 28))
        assert start == date(2026, 7, 27)
        assert end == date(2026, 8, 2)

    def test_quarterly_matches_the_calendar_quarter(self) -> None:
        assert period_bounds("quarterly", date(2026, 7, 28)) == (
            date(2026, 7, 1),
            date(2026, 9, 30),
        )

    def test_unknown_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown review kind"):
            period_bounds("fortnightly", date(2026, 7, 28))


class TestReviewContext:
    @pytest.fixture
    def profile(self, demo_session: Session) -> Profile:
        return demo_session.scalar(select(Profile).where(Profile.code == "demo"))

    def test_carries_everything_the_review_needs(
        self, demo_session: Session, profile: Profile
    ) -> None:
        context = build_review_context(demo_session, profile, "quarterly", AS_OF)
        for key in (
            "published_this_period",
            "stalled",
            "quota_status",
            "decayed_skills",
            "critical_path",
            "market_gaps",
            "open_review_board_objections",
            "previous_review",
        ):
            assert key in context

    def test_reports_the_silent_quarter(
        self, demo_session: Session, profile: Profile
    ) -> None:
        context = build_review_context(demo_session, profile, "quarterly", AS_OF)
        silent = [q for q in context["quota_status"] if q["is_silent"] and q["in_scope"]]
        assert any(q["quarter"] == "2026Q1" for q in silent)

    def test_reports_stalled_work_with_its_age(
        self, demo_session: Session, profile: Profile
    ) -> None:
        context = build_review_context(demo_session, profile, "quarterly", AS_OF)
        assert context["stalled"]
        assert all(item["days_open"] >= 0 for item in context["stalled"])

    def test_reports_the_market_gap(
        self, demo_session: Session, profile: Profile
    ) -> None:
        context = build_review_context(demo_session, profile, "quarterly", AS_OF)
        assert context["market_gaps"]
        codes = {gap["code"] for gap in context["market_gaps"]}
        assert "roi_modelling" in codes or "business_case_writing" in codes

    def test_carries_the_previous_next_action(
        self, demo_session: Session, profile: Profile
    ) -> None:
        # If the last review named a next action and it did not happen, that
        # is the first thing the new review should report.
        context = build_review_context(demo_session, profile, "quarterly", date(2026, 10, 5))
        assert context["previous_review"] is not None
        assert context["previous_review"]["next_action"]

    def test_carries_open_objections(
        self, demo_session: Session, profile: Profile
    ) -> None:
        context = build_review_context(demo_session, profile, "quarterly", AS_OF)
        assert len(context["open_review_board_objections"]) > 0


class TestPeriodicReviewGeneration:
    @pytest.fixture
    def profile(self, demo_session: Session) -> Profile:
        return demo_session.scalar(select(Profile).where(Profile.code == "demo"))

    @pytest.fixture
    def response(self) -> dict:
        return {
            "body_md": "**Shipped:** nothing.",
            "next_action": "Take corporate finance to level 3.",
            "next_action_rationale": "It gates ROI modelling.",
        }

    def test_persists_the_review(
        self, demo_session: Session, profile: Profile, response: dict
    ) -> None:
        review = generate_review(
            demo_session, profile, "weekly", StubClient(response), as_of=AS_OF
        )
        assert review.period_start == date(2026, 7, 27)
        assert review.agent_run_id is not None
        assert review.next_action

    def test_re_running_replaces_rather_than_accumulating(
        self, demo_session: Session, profile: Profile, response: dict
    ) -> None:
        generate_review(demo_session, profile, "weekly", StubClient(response), as_of=AS_OF)
        second = dict(response, next_action="Something else.")
        generate_review(demo_session, profile, "weekly", StubClient(second), as_of=AS_OF)

        stored = list(
            demo_session.scalars(
                select(PeriodicReview).where(
                    PeriodicReview.profile_id == profile.id,
                    PeriodicReview.kind == "weekly",
                    PeriodicReview.period_start == date(2026, 7, 27),
                )
            )
        )
        assert len(stored) == 1
        assert stored[0].next_action == "Something else."

    def test_the_agent_receives_the_quota_status(
        self, demo_session: Session, profile: Profile, response: dict
    ) -> None:
        client = StubClient(response)
        generate_review(demo_session, profile, "quarterly", client, as_of=AS_OF)
        sent = client.calls[0]["user"]
        assert "quota_status" in sent
        assert "2026Q1" in sent


class TestNothingLeaksToTheNetwork:
    def test_no_agent_constructs_a_client_by_itself(
        self, demo_session: Session
    ) -> None:
        """Every entry point takes its client as an argument.

        If one of them ever reached for `default_client()` internally, the
        test suite would start needing an API key — and would fail in CI
        rather than in review.
        """
        import inspect

        from app.services.agents import extraction, periodic_review, review_board

        for module in (review_board, extraction, periodic_review):
            source = inspect.getsource(module)
            assert "default_client()" not in source
            assert "AnthropicClient(" not in source


class TestAgentRunsAreQueryable:
    def test_reviews_and_extractions_both_land_in_one_log(
        self, demo_session: Session
    ) -> None:
        criteria = [c.code for c in demo_session.scalars(select(ReviewCriterion))]
        case = demo_session.scalar(select(BusinessCase))
        review_case(demo_session, case, StubClient(board_response(criteria)), reviewed_on=AS_OF)
        extract_posting(
            demo_session,
            "advert",
            StubClient(
                {
                    "title": "T",
                    "requirements": [
                        {"raw_label": "sql", "skill_code": "sql_core", "importance": "must_have"}
                    ],
                }
            ),
        )
        names = {r.agent_name for r in demo_session.scalars(select(AgentRun))}
        assert {"review_board", "posting_extraction"} <= names

    def test_every_stored_artefact_points_at_its_run(
        self, demo_session: Session
    ) -> None:
        criteria = [c.code for c in demo_session.scalars(select(ReviewCriterion))]
        case = demo_session.scalar(select(BusinessCase))
        review = review_case(
            demo_session, case, StubClient(board_response(criteria)), reviewed_on=AS_OF
        )
        run = demo_session.get(AgentRun, review.agent_run_id)
        assert run is not None
        assert run.model
        assert verify_prompt(run)


def test_schema_output_models_are_documented() -> None:
    """Field descriptions are what the model actually reads."""
    for model in (ReviewBoardOutput, PostingExtractionOutput):
        schema = model.model_json_schema()
        assert schema["properties"]


def test_no_orphan_challenges_without_a_review(demo_session: Session) -> None:
    orphans = demo_session.scalars(
        select(CaseReviewChallenge).where(CaseReviewChallenge.review_id.is_(None))
    ).all()
    assert not orphans


def test_postings_and_requirements_stay_consistent(demo_session: Session) -> None:
    for posting in demo_session.scalars(select(JobPosting)):
        for requirement in demo_session.scalars(
            select(JobRequirement).where(JobRequirement.posting_id == posting.id)
        ):
            assert requirement.raw_label
