"""Gap Radar: what the market asks for, against what the profile holds.

The aggregation deliberately keeps two different numbers apart.

`demand_count` is how many captured postings ask for a skill at all — how
*common* the requirement is. `demanded_level` is the highest level any of them
asks for — how *deep* the deepest ask goes. A skill demanded by one posting at
level 4 and a skill demanded by nine at level 3 are different problems, and a
single blended score would hide which is which.

Unmapped requirements are counted separately and never discarded. A
requirement the taxonomy cannot express is the most interesting output of the
whole module: it means the market has moved somewhere the taxonomy has not.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import JobPosting, JobRequirement, Skill, SkillState, TargetRole


@dataclass(frozen=True)
class SkillDemand:
    skill_code: str
    skill_name: str
    domain_name: str
    demand_count: int
    must_have_count: int
    demanded_level: int | None
    current_level: int
    target_level: int

    @property
    def market_gap(self) -> int:
        """Levels short of what the deepest posting asks for."""
        if self.demanded_level is None:
            return 0
        return max(0, self.demanded_level - self.current_level)

    @property
    def is_critical(self) -> bool:
        """Demanded as a must-have by more than one posting, and short."""
        return self.market_gap > 0 and self.must_have_count >= 2


@dataclass(frozen=True)
class MarketGapReport:
    target_role_code: str | None
    postings_analysed: int
    demands: list[SkillDemand] = field(default_factory=list)
    # Requirements the taxonomy could not express, with how often they appeared.
    unmapped: list[tuple[str, int]] = field(default_factory=list)

    @property
    def critical(self) -> list[SkillDemand]:
        return [demand for demand in self.demands if demand.is_critical]


def market_gaps(
    session: Session,
    profile_id: int,
    target_role_code: str | None = None,
) -> MarketGapReport:
    query = (
        select(JobRequirement)
        .options(selectinload(JobRequirement.skill).selectinload(Skill.domain))
        .join(JobPosting)
    )
    if target_role_code:
        role = session.scalar(select(TargetRole).where(TargetRole.code == target_role_code))
        if role is None:
            raise ValueError(f"unknown target role '{target_role_code}'")
        query = query.where(JobPosting.target_role_id == role.id)

    requirements = list(session.scalars(query))

    postings = {r.posting_id for r in requirements}
    states = {
        s.skill_id: s
        for s in session.scalars(select(SkillState).where(SkillState.profile_id == profile_id))
    }

    by_skill: dict[int, list[JobRequirement]] = {}
    unmapped: Counter[str] = Counter()
    for requirement in requirements:
        if requirement.skill_id is None:
            unmapped[requirement.raw_label] += 1
            continue
        by_skill.setdefault(requirement.skill_id, []).append(requirement)

    demands: list[SkillDemand] = []
    for skill_id, group in by_skill.items():
        skill = group[0].skill
        assert skill is not None
        state = states.get(skill_id)
        levels = [r.required_level for r in group if r.required_level is not None]
        demands.append(
            SkillDemand(
                skill_code=skill.code,
                skill_name=skill.name,
                domain_name=skill.domain.name,
                demand_count=len(group),
                must_have_count=sum(1 for r in group if r.importance == "must_have"),
                demanded_level=max(levels) if levels else None,
                current_level=state.current_level if state else 0,
                target_level=state.target_level if state else 0,
            )
        )

    demands.sort(key=lambda d: (-d.market_gap, -d.must_have_count, d.skill_code))

    return MarketGapReport(
        target_role_code=target_role_code,
        postings_analysed=len(postings),
        demands=demands,
        unmapped=unmapped.most_common(),
    )
