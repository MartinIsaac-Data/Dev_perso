"""The seed files are part of the product, so they are tested like code.

The taxonomy is the substrate every other module reads. A cycle in it, an edge
pointing at a skill that no longer exists, or a rubric whose weights no longer
sum to one would each corrupt every downstream answer while looking perfectly
healthy in the interface.

The demo fixture is tested for arithmetic consistency for a blunter reason: it
is what gets shown to other people, and a worked example whose numbers do not
add up argues against the method it is meant to demonstrate.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Assumption,
    BusinessCase,
    CaseReview,
    CaseReviewScore,
    CauseDriver,
    CauseNode,
    Deliverable,
    DeliverableQuota,
    Phase,
    Profile,
    ReviewCriterion,
    Skill,
    SkillEdge,
    SkillLevelChange,
    SkillState,
)
from app.services.graph import assert_acyclic, find_cycle
from app.services.seeding import seed_reference
from tests.conftest import SEEDS_DIR


class TestTaxonomyFile:
    """Checks against the YAML, before it ever reaches a database."""

    @pytest.fixture
    def taxonomy(self) -> dict:
        with (SEEDS_DIR / "reference" / "skills.yaml").open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def test_skill_codes_are_unique(self, taxonomy: dict) -> None:
        codes = [s["code"] for s in taxonomy["skills"]]
        assert len(codes) == len(set(codes)), "duplicate skill codes in skills.yaml"

    def test_every_skill_belongs_to_a_declared_domain(self, taxonomy: dict) -> None:
        domains = {d["code"] for d in taxonomy["domains"]}
        unknown = {s["domain"] for s in taxonomy["skills"]} - domains
        assert not unknown, f"skills reference undeclared domains: {sorted(unknown)}"

    def test_every_edge_references_declared_skills(self, taxonomy: dict) -> None:
        codes = {s["code"] for s in taxonomy["skills"]}
        unknown = {
            code for e in taxonomy["edges"] for code in (e["from"], e["to"]) if code not in codes
        }
        assert not unknown, f"edges reference undeclared skills: {sorted(unknown)}"

    def test_taxonomy_is_acyclic(self, taxonomy: dict) -> None:
        cycle = find_cycle([(e["from"], e["to"]) for e in taxonomy["edges"]])
        assert cycle is None, f"cycle in the taxonomy: {' -> '.join(cycle or [])}"

    def test_no_duplicate_edges(self, taxonomy: dict) -> None:
        pairs = [(e["from"], e["to"]) for e in taxonomy["edges"]]
        assert len(pairs) == len(set(pairs))

    def test_decay_months_are_plausible(self, taxonomy: dict) -> None:
        for skill in taxonomy["skills"]:
            months = skill.get("decay_months")
            if months is not None:
                assert 3 <= months <= 60, f"{skill['code']}: implausible decay {months}"


class TestReferenceSeed:
    def test_review_criterion_weights_sum_to_one(self, seeded_session: Session) -> None:
        # If they drift, every overall_score becomes incomparable with every
        # score recorded before the drift.
        total = sum(
            c.weight for c in seeded_session.scalars(select(ReviewCriterion))
        )
        assert total == Decimal("1.0000")

    def test_stored_graph_is_acyclic(self, seeded_session: Session) -> None:
        edges = [
            (e.prerequisite_skill_id, e.dependent_skill_id)
            for e in seeded_session.scalars(select(SkillEdge))
        ]
        assert_acyclic(edges)

    def test_phases_do_not_overlap_and_are_contiguous(self, seeded_session: Session) -> None:
        phases = list(seeded_session.scalars(select(Phase).order_by(Phase.ordinal)))
        assert len(phases) >= 2
        for earlier, later in zip(phases, phases[1:], strict=False):
            assert earlier.ends_on < later.starts_on, (
                f"phases {earlier.code} and {later.code} overlap"
            )

    def test_every_phase_has_at_least_one_quota(self, seeded_session: Session) -> None:
        for phase in seeded_session.scalars(select(Phase)):
            count = seeded_session.scalar(
                select(func.count())
                .select_from(DeliverableQuota)
                .where(DeliverableQuota.phase_id == phase.id)
            )
            assert count > 0, f"phase {phase.code} has no quota"

    def test_certifications_alone_never_satisfy_a_later_phase(
        self, seeded_session: Session
    ) -> None:
        # A trajectory that can be satisfied by passing exams produces a
        # certified person nobody hires as an architect.
        for phase in seeded_session.scalars(select(Phase).where(Phase.ordinal > 1)):
            quotas = list(
                seeded_session.scalars(
                    select(DeliverableQuota).where(DeliverableQuota.phase_id == phase.id)
                )
            )
            non_certification = [
                q
                for q in quotas
                if q.deliverable_type.code != "certification" and q.min_per_quarter > 0
            ]
            assert non_certification, f"phase {phase.code} is satisfiable by exams alone"

    def test_seed_is_idempotent(self, seeded_session: Session) -> None:
        before = (
            seeded_session.scalar(select(func.count()).select_from(Skill)),
            seeded_session.scalar(select(func.count()).select_from(SkillEdge)),
        )
        seed_reference(seeded_session, SEEDS_DIR)
        seeded_session.commit()
        after = (
            seeded_session.scalar(select(func.count()).select_from(Skill)),
            seeded_session.scalar(select(func.count()).select_from(SkillEdge)),
        )
        assert before == after


class TestDemoFixture:
    def test_demo_profile_is_flagged_as_demo(self, demo_session: Session) -> None:
        # The whole demo/real separation rests on this one boolean.
        profile = demo_session.scalar(select(Profile).where(Profile.code == "demo"))
        assert profile is not None
        assert profile.is_demo is True

    def test_demo_seed_is_repeatable_without_duplicating(
        self, demo_session: Session
    ) -> None:
        from app.services.seeding import seed_demo

        before = demo_session.scalar(select(func.count()).select_from(Deliverable))
        seed_demo(demo_session, SEEDS_DIR)
        demo_session.commit()
        after = demo_session.scalar(select(func.count()).select_from(Deliverable))
        assert before == after

    def test_every_promotion_in_the_demo_cites_a_deliverable(
        self, demo_session: Session
    ) -> None:
        promotions = [
            c
            for c in demo_session.scalars(select(SkillLevelChange))
            if c.to_level > c.from_level
        ]
        assert promotions, "the demo must exercise the evidence rule"
        assert all(c.deliverable_id is not None for c in promotions)

    def test_demo_contains_a_recorded_downgrade(self, demo_session: Session) -> None:
        # The fixture is meant to be honest, not flattering.
        downgrades = [
            c
            for c in demo_session.scalars(select(SkillLevelChange))
            if c.to_level < c.from_level
        ]
        assert downgrades, "a demo where nothing ever decays demonstrates nothing"

    def test_demo_has_a_quarter_with_no_published_deliverable(
        self, demo_session: Session
    ) -> None:
        # Q1 2026 is deliberately empty so the quota alert has something to
        # find on a fresh install.
        published = [
            d.published_on
            for d in demo_session.scalars(select(Deliverable))
            if d.published_on is not None
        ]
        quarters = {(d.year, (d.month - 1) // 3 + 1) for d in published}
        assert (2026, 1) not in quarters

    def test_demo_skill_states_reference_real_skills(self, demo_session: Session) -> None:
        states = list(demo_session.scalars(select(SkillState)))
        assert len(states) > 30
        skill_ids = {s.id for s in demo_session.scalars(select(Skill))}
        assert all(state.skill_id in skill_ids for state in states)

    def test_current_level_never_exceeds_target(self, demo_session: Session) -> None:
        for state in demo_session.scalars(select(SkillState)):
            assert state.current_level <= state.target_level, (
                f"skill_state {state.skill_id}: current above target"
            )


class TestDemoBusinessCaseArithmetic:
    """The worked example must actually work."""

    @pytest.fixture
    def case(self, demo_session: Session) -> BusinessCase:
        return demo_session.scalar(select(BusinessCase))

    def test_leaf_values_are_the_product_of_their_drivers(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        leaves = self._leaf_values(demo_session, case)
        assert len(leaves) == 5
        # Spot-check one branch against the figure stated in the fixture's
        # own header comment: 412000 * 0.061 * 44.
        assert leaves["Margin lost on unfilled order lines"] == Decimal("1105808.000")

    def test_bottom_up_total_falls_short_of_the_claimed_loss(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        # The gap is the point of the example. If a future edit accidentally
        # reconciles it, the demo loses its most instructive feature.
        total = sum(self._leaf_values(demo_session, case).values())
        assert total == Decimal("3492608.000")
        gap = case.claimed_annual_loss - total
        assert gap > 0
        assert Decimal("0.15") < gap / case.claimed_annual_loss < Decimal("0.20")

    def test_every_roi_line_traces_to_an_assumption(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        from app.models import RoiLine, RoiModel

        models = list(demo_session.scalars(select(RoiModel).where(RoiModel.case_id == case.id)))
        assert models
        for model in models:
            lines = list(
                demo_session.scalars(select(RoiLine).where(RoiLine.roi_model_id == model.id))
            )
            assert lines
            assert all(line.amount_assumption_id is not None for line in lines)

    def test_roi_model_covers_both_costs_and_benefits(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        from app.models import RoiLine, RoiModel

        model = demo_session.scalar(select(RoiModel).where(RoiModel.case_id == case.id))
        lines = list(
            demo_session.scalars(select(RoiLine).where(RoiLine.roi_model_id == model.id))
        )
        categories = {line.category for line in lines}
        # A model missing run cost, licences or change management is the
        # single most common way a ROI case is dishonest.
        assert {"build", "run", "license", "change_management"} <= categories
        assert any(line.kind == "benefit" for line in lines)

    def test_fragile_assumptions_declare_a_range(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        low_confidence = [
            a
            for a in demo_session.scalars(
                select(Assumption).where(Assumption.case_id == case.id)
            )
            if a.confidence == "low"
        ]
        assert low_confidence, "the example must contain admitted weak points"
        for assumption in low_confidence:
            assert assumption.low_value is not None
            assert assumption.high_value is not None
            assert assumption.low_value <= assumption.base_value <= assumption.high_value

    def test_stored_review_score_matches_the_weighted_rubric(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        review = demo_session.scalar(select(CaseReview).where(CaseReview.case_id == case.id))
        assert review is not None
        scores = list(
            demo_session.scalars(
                select(CaseReviewScore).where(CaseReviewScore.review_id == review.id)
            )
        )
        assert len(scores) == 5, "every criterion must be scored"
        weighted = sum(s.score * s.criterion.weight for s in scores)
        assert round(weighted, 2) == review.overall_score

    def test_review_challenges_target_named_assumptions(
        self, demo_session: Session, case: BusinessCase
    ) -> None:
        from app.models import CaseReviewChallenge

        review = demo_session.scalar(select(CaseReview).where(CaseReview.case_id == case.id))
        challenges = list(
            demo_session.scalars(
                select(CaseReviewChallenge).where(CaseReviewChallenge.review_id == review.id)
            )
        )
        assert len(challenges) >= 5
        pinned = [c for c in challenges if c.target_assumption_id is not None]
        assert pinned, "an objection pinned to an assumption is answerable; prose is not"
        assert {c.persona for c in challenges} == {"cfo", "coo", "cio"}
        assert any(c.severity == "blocking" for c in challenges)

    @staticmethod
    def _leaf_values(session: Session, case: BusinessCase) -> dict[str, Decimal]:
        values: dict[str, Decimal] = {}
        for node in session.scalars(select(CauseNode).where(CauseNode.case_id == case.id)):
            drivers = list(
                session.scalars(select(CauseDriver).where(CauseDriver.cause_node_id == node.id))
            )
            if not drivers:
                continue
            value = Decimal(1)
            for driver in drivers:
                value *= session.get(Assumption, driver.assumption_id).base_value
            values[node.label] = value
        return values
