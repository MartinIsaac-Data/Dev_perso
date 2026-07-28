"""Quota arithmetic, evidence rules and the promotion path.

The promotion tests matter most. The database guarantees a promotion carries
*some* deliverable; the service is what stops that deliverable being an
unpublished draft, somebody else's work, or a project that had nothing to do
with the skill being claimed. Without these checks the evidence rule is
satisfiable by pointing at any row in the table, and the whole system's
central claim becomes decorative.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deliverable, DeliverableSkill, DeliverableType, Profile, Skill, SkillState
from app.services.deliverables import (
    EvidenceError,
    evidence_cv,
    iter_quarters,
    quarter_bounds,
    quarter_of,
    quota_status,
    record_level_change,
    touch_skills_from_deliverable,
)

AS_OF = date(2026, 7, 28)


class TestCalendar:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2026, 1, 1), 1),
            (date(2026, 3, 31), 1),
            (date(2026, 4, 1), 2),
            (date(2026, 9, 30), 3),
            (date(2026, 10, 1), 4),
            (date(2026, 12, 31), 4),
        ],
    )
    def test_quarter_of(self, day: date, expected: int) -> None:
        assert quarter_of(day) == expected

    @pytest.mark.parametrize(
        ("year", "quarter", "start", "end"),
        [
            (2026, 1, date(2026, 1, 1), date(2026, 3, 31)),
            (2026, 2, date(2026, 4, 1), date(2026, 6, 30)),
            (2026, 3, date(2026, 7, 1), date(2026, 9, 30)),
            (2026, 4, date(2026, 10, 1), date(2026, 12, 31)),
            # Leap year: Q1 must end on 31 March regardless.
            (2028, 1, date(2028, 1, 1), date(2028, 3, 31)),
        ],
    )
    def test_quarter_bounds(self, year: int, quarter: int, start: date, end: date) -> None:
        assert quarter_bounds(year, quarter) == (start, end)

    def test_iter_quarters_crosses_the_year_boundary(self) -> None:
        quarters = list(iter_quarters(date(2025, 11, 4), date(2026, 5, 2)))
        assert quarters == [(2025, 4), (2026, 1), (2026, 2)]

    def test_iter_quarters_single_quarter(self) -> None:
        assert list(iter_quarters(date(2026, 1, 5), date(2026, 2, 5))) == [(2026, 1)]


class TestQuotaStatus:
    def test_flags_the_silent_quarter(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        # Q1 2026 is deliberately empty in the fixture.
        statuses = {
            (s.year, s.quarter): s
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=8)
        }
        assert statuses[(2026, 1)].is_silent
        assert statuses[(2026, 1)].total_published == 0
        assert not statuses[(2026, 1)].met

    def test_a_quarter_with_output_is_not_silent(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        statuses = {
            (s.year, s.quarter): s
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=8)
        }
        assert not statuses[(2026, 2)].is_silent
        assert statuses[(2026, 2)].total_published > 0

    def test_shortfall_is_reported_per_type(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        statuses = {
            (s.year, s.quarter): s
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=8)
        }
        q2 = statuses[(2026, 2)]
        missed = {line.type_code: line for line in q2.lines if not line.met}
        # A project and a talk shipped, no article did.
        assert "article" in missed
        assert missed["article"].shortfall == 1

    def test_current_quarter_is_marked(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        statuses = quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=4)
        current = [s for s in statuses if s.is_current]
        assert len(current) == 1
        assert (current[0].year, current[0].quarter) == (2026, 3)

    def test_returns_the_requested_number_of_quarters(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        assert len(quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=6)) == 6

    def test_quarters_outside_any_phase_have_no_quota_lines(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        # The trajectory starts in 2026; 2025 quarters predate every phase.
        statuses = {
            (s.year, s.quarter): s
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=8)
        }
        assert statuses[(2025, 4)].phase_code is None
        assert statuses[(2025, 4)].lines == []

    def test_quarters_before_the_trajectory_are_out_of_scope(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        """A quarter that predates the plan cannot fail it.

        Without this distinction the history that existed before the
        trajectory began is reported as a run of silent quarters — a metric
        that punishes the past for not having had a target.
        """
        statuses = {
            (s.year, s.quarter): s
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=10)
        }
        assert statuses[(2025, 2)].is_silent, "factually nothing was published"
        assert not statuses[(2025, 2)].in_scope, "but nothing was asked of it either"
        assert not statuses[(2025, 4)].in_scope

    def test_quarters_inside_a_phase_are_in_scope(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        statuses = {
            (s.year, s.quarter): s
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=8)
        }
        assert statuses[(2026, 1)].in_scope
        assert statuses[(2026, 1)].is_silent, "Q1 2026 is the real silent quarter"

    def test_unpublished_work_never_counts(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        # The Fabric proof of concept is in_progress in Q3 2026.
        before = {
            (s.year, s.quarter): s.total_published
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=4)
        }
        in_progress = demo_session.scalar(
            select(Deliverable).where(
                Deliverable.profile_id == demo_profile_id,
                Deliverable.status == "in_progress",
            )
        )
        assert in_progress is not None
        after = {
            (s.year, s.quarter): s.total_published
            for s in quota_status(demo_session, demo_profile_id, AS_OF, quarters_back=4)
        }
        assert before == after


class TestPromotion:
    @pytest.fixture
    def skill_id(self, demo_session: Session) -> int:
        return demo_session.scalar(select(Skill.id).where(Skill.code == "microsoft_fabric"))

    @pytest.fixture
    def published_deliverable(self, demo_session: Session, demo_profile_id: int) -> Deliverable:
        return demo_session.scalar(
            select(Deliverable).where(
                Deliverable.profile_id == demo_profile_id,
                Deliverable.title.like("ERP to lakehouse%"),
            )
        )

    def test_promotion_without_evidence_is_refused(
        self, demo_session: Session, demo_profile_id: int, skill_id: int
    ) -> None:
        with pytest.raises(EvidenceError, match="only rises against evidence"):
            record_level_change(
                demo_session, profile_id=demo_profile_id, skill_id=skill_id, to_level=3
            )

    def test_evidence_must_be_published(
        self, demo_session: Session, demo_profile_id: int, skill_id: int
    ) -> None:
        draft = demo_session.scalar(
            select(Deliverable).where(
                Deliverable.profile_id == demo_profile_id,
                Deliverable.status == "in_progress",
            )
        )
        with pytest.raises(EvidenceError, match="must be published"):
            record_level_change(
                demo_session,
                profile_id=demo_profile_id,
                skill_id=skill_id,
                to_level=3,
                deliverable_id=draft.id,
            )

    def test_evidence_must_exercise_the_skill(
        self,
        demo_session: Session,
        demo_profile_id: int,
        published_deliverable: Deliverable,
    ) -> None:
        # The ingestion project is real and published, but it has nothing to
        # do with executive communication.
        unrelated = demo_session.scalar(
            select(Skill.id).where(Skill.code == "executive_communication")
        )
        with pytest.raises(EvidenceError, match="does not exercise this skill"):
            record_level_change(
                demo_session,
                profile_id=demo_profile_id,
                skill_id=unrelated,
                to_level=4,
                deliverable_id=published_deliverable.id,
            )

    def test_evidence_must_belong_to_the_same_profile(
        self, demo_session: Session, published_deliverable: Deliverable
    ) -> None:
        other = Profile(code="other", display_name="Other", is_demo=False)
        demo_session.add(other)
        demo_session.flush()
        skill_id = demo_session.scalar(select(Skill.id).where(Skill.code == "etl_design"))
        with pytest.raises(EvidenceError, match="different profile"):
            record_level_change(
                demo_session,
                profile_id=other.id,
                skill_id=skill_id,
                to_level=3,
                deliverable_id=published_deliverable.id,
            )

    def test_valid_promotion_updates_state_and_history(
        self,
        demo_session: Session,
        demo_profile_id: int,
        published_deliverable: Deliverable,
    ) -> None:
        skill_id = demo_session.scalar(select(Skill.id).where(Skill.code == "file_formats"))
        change = record_level_change(
            demo_session,
            profile_id=demo_profile_id,
            skill_id=skill_id,
            to_level=3,
            deliverable_id=published_deliverable.id,
            rationale="Partitioning strategy chosen and defended.",
        )
        assert change.from_level == 2
        assert change.to_level == 3

        state = demo_session.scalar(
            select(SkillState).where(
                SkillState.profile_id == demo_profile_id, SkillState.skill_id == skill_id
            )
        )
        assert state.current_level == 3
        # The decay clock is reset from the evidence, not from today.
        assert state.last_practised_on == published_deliverable.published_on

    def test_downgrade_requires_nothing(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        skill_id = demo_session.scalar(select(Skill.id).where(Skill.code == "dax"))
        change = record_level_change(
            demo_session,
            profile_id=demo_profile_id,
            skill_id=skill_id,
            to_level=2,
            rationale="Could not explain context transition unaided.",
        )
        assert change.to_level == 2
        assert change.deliverable_id is None

    def test_out_of_range_level_is_refused(
        self, demo_session: Session, demo_profile_id: int, skill_id: int
    ) -> None:
        with pytest.raises(EvidenceError, match="between 0 and 5"):
            record_level_change(
                demo_session, profile_id=demo_profile_id, skill_id=skill_id, to_level=7
            )


class TestPracticeTracking:
    def test_publishing_refreshes_the_decay_clock(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        skill = demo_session.scalar(select(Skill).where(Skill.code == "report_design"))
        state = demo_session.scalar(
            select(SkillState).where(
                SkillState.profile_id == demo_profile_id, SkillState.skill_id == skill.id
            )
        )
        stale = state.last_practised_on

        type_ = demo_session.scalar(
            select(DeliverableType).where(DeliverableType.code == "article")
        )
        deliverable = Deliverable(
            profile_id=demo_profile_id,
            type_id=type_.id,
            title="Dashboard layout for operations",
            status="published",
            published_on=date(2026, 7, 20),
        )
        demo_session.add(deliverable)
        demo_session.flush()
        demo_session.add(
            DeliverableSkill(
                deliverable_id=deliverable.id, skill_id=skill.id, contribution=3
            )
        )
        demo_session.flush()

        assert touch_skills_from_deliverable(demo_session, deliverable) == 1
        demo_session.refresh(state)
        assert state.last_practised_on == date(2026, 7, 20)
        assert state.last_practised_on > stale

    def test_unpublished_work_does_not_reset_the_clock(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        type_ = demo_session.scalar(
            select(DeliverableType).where(DeliverableType.code == "project")
        )
        draft = Deliverable(
            profile_id=demo_profile_id,
            type_id=type_.id,
            title="Draft",
            status="in_progress",
        )
        demo_session.add(draft)
        demo_session.flush()
        assert touch_skills_from_deliverable(demo_session, draft) == 0


class TestEvidenceCv:
    def test_flags_levels_with_nothing_behind_them(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        rows = evidence_cv(demo_session, demo_profile_id, min_level=3)
        undefensible = [r for r in rows if not r.is_defensible]
        assert undefensible, "the demo must contain claims an interviewer would find"
        assert all(r.current_level >= 3 for r in undefensible)
        assert all(not any(e.published_on for e in r.evidence) for r in undefensible)

    def test_marks_deliverables_cited_for_promotion(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        rows = {r.skill_code: r for r in evidence_cv(demo_session, demo_profile_id, min_level=2)}
        dax = rows["dax"]
        cited = [e for e in dax.evidence if e.cited_for_promotion]
        assert cited, "the DAX promotion cited an article; it must be marked as such"

    def test_respects_the_minimum_level(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        rows = evidence_cv(demo_session, demo_profile_id, min_level=4)
        assert rows
        assert all(r.current_level >= 4 for r in rows)

    def test_ordered_by_level_descending(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        levels = [r.current_level for r in evidence_cv(demo_session, demo_profile_id)]
        assert levels == sorted(levels, reverse=True)
