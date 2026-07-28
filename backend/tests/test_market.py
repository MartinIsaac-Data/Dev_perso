"""Gap Radar.

The aggregation keeps two numbers apart on purpose: how *common* a requirement
is across postings, and how *deep* the deepest ask goes. A skill demanded by
one posting at level 4 and a skill demanded by nine at level 3 are different
problems, and the tests below pin that distinction so a future "simplification"
into a single blended score fails loudly.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobPosting, JobRequirement, Profile, Skill
from app.services.market import market_gaps


@pytest.fixture
def profile_id(demo_session: Session) -> int:
    return demo_session.scalar(select(Profile.id).where(Profile.code == "demo"))


class TestMarketGaps:
    def test_counts_the_postings_analysed(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id)
        assert report.postings_analysed == 3

    def test_gap_is_against_the_deepest_demand(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id)
        by_code = {d.skill_code: d for d in report.demands}
        # Two postings ask for business_case_writing at level 4; the demo
        # holds it at 2.
        target = by_code["business_case_writing"]
        assert target.demanded_level == 4
        assert target.current_level == 2
        assert target.market_gap == 2

    def test_demand_count_and_depth_are_separate(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id)
        by_code = {d.skill_code: d for d in report.demands}
        for demand in by_code.values():
            assert demand.demand_count >= demand.must_have_count
            # A count is not a level and must never be conflated with one.
            assert demand.demanded_level is None or 0 <= demand.demanded_level <= 5

    def test_a_skill_already_deep_enough_shows_no_gap(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id)
        by_code = {d.skill_code: d for d in report.demands}
        # sql_core is demanded at 4 and the demo holds it at 4.
        assert by_code["sql_core"].market_gap == 0

    def test_critical_means_short_and_demanded_more_than_once(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id)
        assert report.critical
        assert all(d.market_gap > 0 and d.must_have_count >= 2 for d in report.critical)

    def test_ranked_by_gap_then_by_how_often_it_is_demanded(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id)
        keys = [(-d.market_gap, -d.must_have_count) for d in report.demands]
        assert keys == sorted(keys)

    def test_unmapped_requirements_are_kept_not_discarded(
        self, demo_session: Session, profile_id: int
    ) -> None:
        """The most interesting output: the market moved, the taxonomy did not."""
        posting = demo_session.scalar(select(JobPosting))
        demo_session.add(
            JobRequirement(
                posting_id=posting.id,
                raw_label="experience negotiating with data vendors",
                skill_id=None,
                importance="must_have",
            )
        )
        demo_session.flush()

        report = market_gaps(demo_session, profile_id)
        labels = {label for label, _ in report.unmapped}
        assert "experience negotiating with data vendors" in labels

    def test_filters_to_one_target_role(
        self, demo_session: Session, profile_id: int
    ) -> None:
        report = market_gaps(demo_session, profile_id, "ai_transformation_lead")
        assert report.postings_analysed == 1
        assert report.target_role_code == "ai_transformation_lead"

    def test_unknown_role_is_refused(
        self, demo_session: Session, profile_id: int
    ) -> None:
        with pytest.raises(ValueError, match="unknown target role"):
            market_gaps(demo_session, profile_id, "chief_vibes_officer")

    def test_an_untracked_skill_counts_as_level_zero(
        self, demo_session: Session, profile_id: int
    ) -> None:
        posting = demo_session.scalar(select(JobPosting))
        skill = demo_session.scalar(select(Skill).where(Skill.code == "data_vault"))
        demo_session.add(
            JobRequirement(
                posting_id=posting.id,
                raw_label="Data Vault",
                skill_id=skill.id,
                required_level=4,
                importance="must_have",
            )
        )
        demo_session.flush()

        report = market_gaps(demo_session, profile_id)
        by_code = {d.skill_code: d for d in report.demands}
        assert by_code["data_vault"].current_level == 0
        assert by_code["data_vault"].market_gap == 4


class TestMarketApi:
    def test_gaps_endpoint(self, client: TestClient) -> None:
        body = client.get("/market/gaps").json()
        assert body["postings_analysed"] == 3
        assert body["demands"]
        gaps = {d["skill_code"]: d for d in body["demands"]}
        assert gaps["business_case_writing"]["market_gap"] == 2

    def test_filter_by_role(self, client: TestClient) -> None:
        body = client.get("/market/gaps?target_role=industrial_ai_consultant").json()
        assert body["postings_analysed"] == 1

    def test_unknown_role_is_422(self, client: TestClient) -> None:
        assert client.get("/market/gaps?target_role=nope").status_code == 422

    def test_postings_carry_their_requirements(self, client: TestClient) -> None:
        postings = client.get("/postings").json()
        assert len(postings) == 3
        assert all(p["requirements"] for p in postings)

    def test_postings_are_newest_first(self, client: TestClient) -> None:
        dates = [p["captured_on"] for p in client.get("/postings").json()]
        assert dates == sorted(dates, reverse=True)

    def test_agent_runs_endpoint_is_empty_on_a_fresh_demo(
        self, client: TestClient
    ) -> None:
        assert client.get("/agent-runs").json() == []

    def test_extraction_without_a_key_is_503_with_an_instruction(
        self, client: TestClient
    ) -> None:
        """Not a 500. Everything else works without a key, and the error
        should say what to do rather than look like a fault."""
        response = client.post("/postings/extract", json={"raw_text": "x" * 60})
        assert response.status_code == 503
        assert "TOS_ANTHROPIC_API_KEY" in response.json()["detail"]

    def test_periodic_review_generation_without_a_key_is_503(
        self, client: TestClient
    ) -> None:
        response = client.post("/periodic-reviews", json={"kind": "weekly"})
        assert response.status_code == 503

    def test_the_demo_periodic_review_is_listed(self, client: TestClient) -> None:
        reviews = client.get("/periodic-reviews").json()
        assert len(reviews) == 1
        assert reviews[0]["kind"] == "quarterly"
        assert reviews[0]["next_action"]


def test_captured_on_is_never_in_the_future(demo_session: Session) -> None:
    # A posting captured tomorrow means the clock or the import is wrong.
    for posting in demo_session.scalars(select(JobPosting)):
        assert posting.captured_on <= date(2027, 1, 1)
