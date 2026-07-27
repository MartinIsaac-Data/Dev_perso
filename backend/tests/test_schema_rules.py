"""Rules the database itself must enforce.

Every rule tested here is one a service method could also check. The point of
testing them at the database level is that a service method can be bypassed —
by a script, by a future endpoint, by a bulk import — and a CHECK constraint
cannot. If any of these tests starts failing, the schema has stopped
protecting its own invariants.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Deliverable,
    DeliverableType,
    Profile,
    Skill,
    SkillEdge,
    SkillLevelChange,
    SkillState,
)


@pytest.fixture
def profile(session: Session) -> Profile:
    profile = Profile(code="test", display_name="Test", is_demo=False)
    session.add(profile)
    session.flush()
    return profile


class TestEvidenceRule:
    """A level only rises against evidence. The central rule of the system."""

    def test_promotion_without_evidence_is_rejected(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        seeded_session.add(
            SkillLevelChange(
                profile_id=profile.id,
                skill_id=skill.id,
                from_level=2,
                to_level=3,
                changed_on=date(2026, 1, 1),
                deliverable_id=None,
            )
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()

    def test_promotion_with_evidence_is_accepted(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        type_ = seeded_session.scalar(
            select(DeliverableType).where(DeliverableType.code == "project")
        )
        deliverable = Deliverable(
            profile_id=profile.id,
            type_id=type_.id,
            title="Evidence",
            status="published",
            published_on=date(2026, 1, 1),
        )
        seeded_session.add(deliverable)
        seeded_session.flush()

        seeded_session.add(
            SkillLevelChange(
                profile_id=profile.id,
                skill_id=skill.id,
                from_level=2,
                to_level=3,
                changed_on=date(2026, 1, 1),
                deliverable_id=deliverable.id,
            )
        )
        seeded_session.flush()  # must not raise

    def test_downgrade_needs_no_evidence(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        # Admitting decay must never require paperwork, or it goes unrecorded.
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        seeded_session.add(
            SkillLevelChange(
                profile_id=profile.id,
                skill_id=skill.id,
                from_level=3,
                to_level=2,
                changed_on=date(2026, 1, 1),
                deliverable_id=None,
            )
        )
        seeded_session.flush()  # must not raise

    def test_lateral_change_needs_no_evidence(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        seeded_session.add(
            SkillLevelChange(
                profile_id=profile.id,
                skill_id=skill.id,
                from_level=3,
                to_level=3,
                changed_on=date(2026, 1, 1),
                deliverable_id=None,
            )
        )
        seeded_session.flush()


class TestPublishedDeliverables:
    def test_published_without_a_date_is_rejected(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        # Without this, the quarterly quota is uncomputable.
        type_ = seeded_session.scalar(
            select(DeliverableType).where(DeliverableType.code == "article")
        )
        seeded_session.add(
            Deliverable(
                profile_id=profile.id,
                type_id=type_.id,
                title="No date",
                status="published",
                published_on=None,
            )
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()

    def test_in_progress_without_a_date_is_fine(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        type_ = seeded_session.scalar(
            select(DeliverableType).where(DeliverableType.code == "article")
        )
        seeded_session.add(
            Deliverable(
                profile_id=profile.id,
                type_id=type_.id,
                title="Draft",
                status="in_progress",
            )
        )
        seeded_session.flush()

    def test_unknown_status_is_rejected(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        type_ = seeded_session.scalar(
            select(DeliverableType).where(DeliverableType.code == "article")
        )
        seeded_session.add(
            Deliverable(
                profile_id=profile.id,
                type_id=type_.id,
                title="Bad status",
                status="nearly_done",
            )
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()


class TestGraphConstraints:
    def test_self_dependency_is_rejected(self, seeded_session: Session) -> None:
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        seeded_session.add(
            SkillEdge(prerequisite_skill_id=skill.id, dependent_skill_id=skill.id)
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()

    def test_duplicate_edge_is_rejected(self, seeded_session: Session) -> None:
        edge = seeded_session.scalars(select(SkillEdge)).first()
        seeded_session.add(
            SkillEdge(
                prerequisite_skill_id=edge.prerequisite_skill_id,
                dependent_skill_id=edge.dependent_skill_id,
            )
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()

    def test_level_out_of_range_is_rejected(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        seeded_session.add(
            SkillState(
                profile_id=profile.id,
                skill_id=skill.id,
                current_level=7,
                target_level=5,
            )
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()

    def test_one_state_row_per_profile_and_skill(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        skill = seeded_session.scalar(select(Skill).where(Skill.code == "sql_core"))
        seeded_session.add(
            SkillState(profile_id=profile.id, skill_id=skill.id, current_level=1, target_level=3)
        )
        seeded_session.flush()
        seeded_session.add(
            SkillState(profile_id=profile.id, skill_id=skill.id, current_level=2, target_level=4)
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()


class TestForeignKeysAreEnforced:
    def test_dangling_foreign_key_is_rejected(
        self, seeded_session: Session, profile: Profile
    ) -> None:
        # Guards the guard: if the SQLite pragma were ever dropped, every
        # other referential test in this suite would silently stop testing
        # anything. This one fails loudly instead.
        seeded_session.add(
            Deliverable(
                profile_id=profile.id,
                type_id=999_999,
                title="Dangling type",
                status="planned",
            )
        )
        with pytest.raises(IntegrityError):
            seeded_session.flush()
