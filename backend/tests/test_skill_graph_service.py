"""Skill graph queries against a real database.

`test_graph.py` proves the pure functions are correct on graphs where the
right answer is obvious. This file proves the database layer asks them the
right questions — which is a different failure mode: a correct traversal fed
the wrong edge direction produces confident nonsense.

The decay tests deliberately check the boundary rather than the middle. An
off-by-one in a decay window is invisible in normal use and produces alerts a
month early or a month late for years.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Skill, SkillState
from app.services import skill_graph
from app.services.skill_graph import months_between

AS_OF = date(2026, 7, 28)


class TestMonthsBetween:
    def test_whole_months(self) -> None:
        assert months_between(date(2025, 1, 15), date(2025, 7, 15)) == 6

    def test_day_of_month_not_yet_reached(self) -> None:
        # 14 July is not yet six months after 15 January.
        assert months_between(date(2025, 1, 15), date(2025, 7, 14)) == 5

    def test_crosses_year_boundary(self) -> None:
        assert months_between(date(2024, 11, 1), date(2026, 7, 1)) == 20

    def test_future_date_is_zero_not_negative(self) -> None:
        assert months_between(date(2026, 7, 1), date(2026, 1, 1)) == 0

    def test_same_day(self) -> None:
        assert months_between(date(2026, 7, 28), date(2026, 7, 28)) == 0


class TestPositions:
    def test_covers_the_whole_taxonomy(self, demo_session: Session, demo_profile_id: int) -> None:
        positions = skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        total = demo_session.scalar(select(func.count()).select_from(Skill))
        assert len(positions) == total

    def test_untracked_skills_default_to_zero(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        untracked = [p for p in positions.values() if not p.tracked]
        assert untracked, "the demo does not track every skill; some must be untracked"
        assert all(p.current_level == 0 and p.target_level == 0 for p in untracked)
        # Untracked means "not wanted", so they never appear as work to do.
        assert all(p.gap == 0 for p in untracked)

    def test_gap_is_never_negative(self, demo_session: Session, demo_profile_id: int) -> None:
        positions = skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        assert all(p.gap >= 0 for p in positions)


class TestBlocking:
    def test_names_the_specific_unmet_prerequisite(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        # forecasting requires statistics_core at 3; the demo holds it at 2.
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        forecasting = positions["forecasting"]
        assert forecasting.is_blocked
        blockers = {u.code: u for u in forecasting.unmet_prerequisites}
        assert "statistics_core" in blockers
        assert blockers["statistics_core"].current_level == 2
        assert blockers["statistics_core"].required_level == 3

    def test_satisfied_prerequisite_does_not_block(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        # python_data requires python_core at 3; the demo holds it at 3.
        assert not any(
            u.code == "python_core" for u in positions["python_data"].unmet_prerequisites
        )

    def test_raising_a_prerequisite_unblocks_the_dependent(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        """The propagation property: the graph must react to a level change."""
        before = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert before["forecasting"].is_blocked

        state = demo_session.scalar(
            select(SkillState)
            .join(Skill)
            .where(SkillState.profile_id == demo_profile_id, Skill.code == "statistics_core")
        )
        state.current_level = 3
        demo_session.flush()

        after = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert not any(
            u.code == "statistics_core" for u in after["forecasting"].unmet_prerequisites
        )

    def test_available_and_blocked_are_disjoint(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        available = {
            p.code for p in skill_graph.available_now(demo_session, demo_profile_id, AS_OF)
        }
        blocked = {p.code for p in skill_graph.blocked_skills(demo_session, demo_profile_id, AS_OF)}
        assert not (available & blocked)


class TestCriticalPath:
    def test_only_returns_skills_below_target(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        for position in skill_graph.critical_path(demo_session, demo_profile_id, 20, AS_OF):
            assert position.gap > 0

    def test_ordered_by_what_it_blocks(self, demo_session: Session, demo_profile_id: int) -> None:
        path = skill_graph.critical_path(demo_session, demo_profile_id, 10, AS_OF)
        scores = [p.blocks_below_target for p in path]
        assert scores == sorted(scores, reverse=True)

    def test_counts_only_wanted_descendants(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        """A skill gating only satisfied skills scores zero.

        This is the property that distinguishes a critical path from a
        ranking of the taxonomy by centrality.
        """
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        for position in positions.values():
            assert position.blocks_below_target <= position.unlocks_total

    def test_respects_the_limit(self, demo_session: Session, demo_profile_id: int) -> None:
        assert len(skill_graph.critical_path(demo_session, demo_profile_id, 3, AS_OF)) == 3


class TestDecay:
    def _set(self, session: Session, profile_id: int, code: str, **fields: object) -> None:
        state = session.scalar(
            select(SkillState)
            .join(Skill)
            .where(SkillState.profile_id == profile_id, Skill.code == code)
        )
        for key, value in fields.items():
            setattr(state, key, value)
        session.flush()

    def test_demo_reports_decayed_skills(self, demo_session: Session, demo_profile_id: int) -> None:
        # A demo where nothing has decayed does not demonstrate decay.
        decayed = skill_graph.decayed_skills(demo_session, demo_profile_id, AS_OF)
        assert decayed, "the demo fixture must exercise decay detection"
        assert all(p.is_decayed for p in decayed)

    def test_exactly_at_the_window_is_decayed(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        # report_design has an 18-month window.
        self._set(
            demo_session,
            demo_profile_id,
            "report_design",
            last_practised_on=date(2025, 1, 28),
            current_level=3,
        )
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert positions["report_design"].months_since_practice == 18
        assert positions["report_design"].is_decayed

    def test_one_day_short_of_the_window_is_not_decayed(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        self._set(
            demo_session,
            demo_profile_id,
            "report_design",
            last_practised_on=date(2025, 1, 29),
            current_level=3,
        )
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert positions["report_design"].months_since_practice == 17
        assert not positions["report_design"].is_decayed

    def test_low_levels_do_not_decay(self, demo_session: Session, demo_profile_id: int) -> None:
        # Level 1 means "read about it". There is nothing there to rot.
        self._set(
            demo_session,
            demo_profile_id,
            "report_design",
            last_practised_on=date(2020, 1, 1),
            current_level=1,
        )
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert not positions["report_design"].is_decayed

    def test_never_practised_is_not_reported_as_decayed(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        # Null last_practised_on means unknown, not stale.
        self._set(demo_session, demo_profile_id, "report_design", last_practised_on=None)
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert positions["report_design"].months_since_practice is None
        assert not positions["report_design"].is_decayed

    def test_skills_at_target_are_still_reported(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        """The one nobody thinks to check."""
        self._set(
            demo_session,
            demo_profile_id,
            "warehouse_ops",
            last_practised_on=date(2022, 1, 1),
            current_level=4,
            target_level=4,
        )
        decayed = {p.code for p in skill_graph.decayed_skills(demo_session, demo_profile_id, AS_OF)}
        assert "warehouse_ops" in decayed


class TestLearningOrder:
    def test_respects_prerequisites(self, demo_session: Session, demo_profile_id: int) -> None:
        order = skill_graph.learning_order(demo_session, demo_profile_id, AS_OF)
        position = {code: i for i, code in enumerate(order)}
        # Both are in the order, and statistics precedes what it gates.
        if "statistics_core" in position and "forecasting" in position:
            assert position["statistics_core"] < position["forecasting"]

    def test_contains_only_wanted_skills(self, demo_session: Session, demo_profile_id: int) -> None:
        order = set(skill_graph.learning_order(demo_session, demo_profile_id, AS_OF))
        positions = {
            p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        }
        assert all(positions[code].gap > 0 for code in order)


class TestDomainSummary:
    def test_totals_reconcile_with_positions(
        self, demo_session: Session, demo_profile_id: int
    ) -> None:
        summary = skill_graph.domain_summary(demo_session, demo_profile_id, AS_OF)
        positions = skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
        assert sum(row["skills"] for row in summary) == len(positions)
        assert sum(row["total_gap"] for row in summary) == sum(p.gap for p in positions)


@pytest.mark.parametrize("code", ["sql_core", "python_core", "relational_modelling_basics"])
def test_foundational_skills_unlock_many(
    demo_session: Session, demo_profile_id: int, code: str
) -> None:
    """Sanity check on edge direction.

    If the edges were loaded backwards, these roots would unlock nothing and
    the leaves would unlock everything — a mistake that produces a plausible
    looking but exactly inverted critical path.
    """
    positions = {
        p.code: p for p in skill_graph.skill_positions(demo_session, demo_profile_id, AS_OF)
    }
    assert positions[code].unlocks_total > 10
