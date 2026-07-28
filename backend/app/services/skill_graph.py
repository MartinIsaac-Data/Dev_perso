"""Skill graph queries against the database.

This module is the bridge between `services/graph.py` — which knows nothing
about SQLAlchemy and operates on plain node pairs — and the API. It loads
rows, hands pairs to the pure functions, and returns dataclasses.

The four questions it answers, in the order they matter:

  - **Where am I blocked?** A skill is blocked when any prerequisite sits
    below the level that edge requires. Naming the specific unmet
    prerequisites is the useful part; "blocked" alone is not actionable.
  - **What can I start today?** Not blocked, and still below target.
  - **What should I start today?** Of the skills below target, which one gates
    the most other skills that are also below target. That qualifier is what
    makes this a critical path rather than a ranking of the taxonomy by
    popularity — a prerequisite whose dependents are already satisfied blocks
    nothing, however central it looks.
  - **What am I quietly losing?** Skills past their decay window.

Returned as frozen dataclasses rather than ORM objects so the API layer can
serialise them without a lazy load firing mid-response, and so these functions
can be tested without a running application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Skill, SkillDomain, SkillEdge, SkillState
from app.services.graph import blocking_scores, descendants, topological_order

# Below this level there is no meaningful skill to lose, so decay is not
# reported: level 1 means "read about it", and that does not rot the way
# hands-on capability does.
DECAY_FLOOR_LEVEL = 2


@dataclass(frozen=True)
class UnmetPrerequisite:
    skill_id: int
    code: str
    name: str
    required_level: int
    current_level: int


@dataclass(frozen=True)
class SkillPosition:
    """Everything the interface needs about one skill, for one profile."""

    skill_id: int
    code: str
    name: str
    domain_code: str
    domain_name: str
    description: str | None
    current_level: int
    target_level: int
    # False when the profile has no state row: the skill exists in the shared
    # taxonomy but this profile has never assessed it.
    tracked: bool
    last_practised_on: date | None
    decay_months: int
    months_since_practice: int | None
    is_decayed: bool
    # Total skills downstream in the taxonomy, regardless of profile state.
    unlocks_total: int
    # Downstream skills that are *also* below target — the actionable count.
    blocks_below_target: int
    unmet_prerequisites: list[UnmetPrerequisite] = field(default_factory=list)

    @property
    def gap(self) -> int:
        return max(0, self.target_level - self.current_level)

    @property
    def is_blocked(self) -> bool:
        return bool(self.unmet_prerequisites)

    @property
    def is_available(self) -> bool:
        """Below target, and every prerequisite satisfied."""
        return self.gap > 0 and not self.unmet_prerequisites


def months_between(earlier: date, later: date) -> int:
    """Whole months from `earlier` to `later`, never negative.

    Calendar months rather than days/30: a decay window expressed as "nine
    months" should mean nine calendar months, so a skill practised on the 3rd
    of January is due on the 3rd of October regardless of month lengths.
    """
    if later < earlier:
        return 0
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if later.day < earlier.day:
        months -= 1
    return max(0, months)


def load_edges(session: Session) -> list[tuple[int, int]]:
    return [
        (e.prerequisite_skill_id, e.dependent_skill_id)
        for e in session.scalars(select(SkillEdge))
    ]


def skill_positions(
    session: Session,
    profile_id: int,
    as_of: date | None = None,
) -> list[SkillPosition]:
    """Full picture for one profile, one row per skill in the taxonomy.

    Computed in a single pass rather than per skill: the blocking scores need
    the whole graph anyway, and eighty-three round trips to answer one screen
    would be the kind of N+1 this project exists to learn not to write.
    """
    as_of = as_of or date.today()
    default_decay = get_settings().default_skill_decay_months

    skills = list(
        session.scalars(select(Skill).options(selectinload(Skill.domain)).order_by(Skill.code))
    )
    states = {
        s.skill_id: s
        for s in session.scalars(select(SkillState).where(SkillState.profile_id == profile_id))
    }
    edges_raw = list(session.scalars(select(SkillEdge)))
    edges = [(e.prerequisite_skill_id, e.dependent_skill_id) for e in edges_raw]
    by_id = {s.id: s for s in skills}

    current = {s.id: (states[s.id].current_level if s.id in states else 0) for s in skills}
    target = {s.id: (states[s.id].target_level if s.id in states else 0) for s in skills}

    below_target = {sid for sid in current if target[sid] > current[sid]}
    scores = blocking_scores(edges, below_target)

    # Unmet prerequisites, grouped by the skill they block.
    unmet: dict[int, list[UnmetPrerequisite]] = {}
    for edge in edges_raw:
        prerequisite_level = current.get(edge.prerequisite_skill_id, 0)
        if prerequisite_level < edge.required_level:
            prerequisite = by_id.get(edge.prerequisite_skill_id)
            if prerequisite is None:
                continue
            unmet.setdefault(edge.dependent_skill_id, []).append(
                UnmetPrerequisite(
                    skill_id=prerequisite.id,
                    code=prerequisite.code,
                    name=prerequisite.name,
                    required_level=edge.required_level,
                    current_level=prerequisite_level,
                )
            )

    positions: list[SkillPosition] = []
    for skill in skills:
        state = states.get(skill.id)
        decay_months = skill.decay_months or default_decay
        last = state.last_practised_on if state else None
        elapsed = months_between(last, as_of) if last else None
        level = current[skill.id]
        decayed = (
            level >= DECAY_FLOOR_LEVEL
            and elapsed is not None
            and elapsed >= decay_months
        )
        positions.append(
            SkillPosition(
                skill_id=skill.id,
                code=skill.code,
                name=skill.name,
                domain_code=skill.domain.code,
                domain_name=skill.domain.name,
                description=skill.description,
                current_level=level,
                target_level=target[skill.id],
                tracked=state is not None,
                last_practised_on=last,
                decay_months=decay_months,
                months_since_practice=elapsed,
                is_decayed=decayed,
                unlocks_total=len(descendants(edges, skill.id)),
                blocks_below_target=scores.get(skill.id, 0),
                unmet_prerequisites=sorted(
                    unmet.get(skill.id, []), key=lambda p: p.code
                ),
            )
        )
    return positions


def critical_path(
    session: Session,
    profile_id: int,
    limit: int = 10,
    as_of: date | None = None,
) -> list[SkillPosition]:
    """Skills below target, ranked by how much they hold up.

    Ordered by blocked descendants first, then by how far below target the
    skill itself sits, then by code for stability. Available skills come
    before blocked ones at equal weight: recommending something the profile
    cannot start yet is not advice.
    """
    positions = [p for p in skill_positions(session, profile_id, as_of) if p.gap > 0]
    positions.sort(
        key=lambda p: (-p.blocks_below_target, p.is_blocked, -p.gap, p.code),
    )
    return positions[:limit]


def available_now(
    session: Session, profile_id: int, as_of: date | None = None
) -> list[SkillPosition]:
    """Below target with every prerequisite satisfied — startable today."""
    positions = [p for p in skill_positions(session, profile_id, as_of) if p.is_available]
    positions.sort(key=lambda p: (-p.blocks_below_target, -p.gap, p.code))
    return positions


def blocked_skills(
    session: Session, profile_id: int, as_of: date | None = None
) -> list[SkillPosition]:
    positions = [
        p for p in skill_positions(session, profile_id, as_of) if p.gap > 0 and p.is_blocked
    ]
    positions.sort(key=lambda p: (len(p.unmet_prerequisites), p.code))
    return positions


def decayed_skills(
    session: Session, profile_id: int, as_of: date | None = None
) -> list[SkillPosition]:
    """Skills past their decay window, worst overrun first.

    Deliberately not filtered to skills below target. A skill sitting at its
    target that has not been touched in eighteen months is exactly the one
    nobody thinks to check, and the one that will fail in an interview.
    """
    positions = [p for p in skill_positions(session, profile_id, as_of) if p.is_decayed]
    positions.sort(
        key=lambda p: -((p.months_since_practice or 0) - p.decay_months),
    )
    return positions


def learning_order(session: Session, profile_id: int, as_of: date | None = None) -> list[str]:
    """Skill codes below target, in an order that respects prerequisites.

    A topological order over the whole taxonomy, filtered to what is still
    wanted. It is not a schedule — it makes no claim about effort or time —
    but it is a sequence in which nothing is attempted before what it needs.
    """
    positions = {p.skill_id: p for p in skill_positions(session, profile_id, as_of)}
    edges = load_edges(session)
    order = topological_order(edges, nodes=list(positions))
    return [positions[sid].code for sid in order if positions[sid].gap > 0]


def domain_summary(
    session: Session, profile_id: int, as_of: date | None = None
) -> list[dict[str, object]]:
    """Aggregate position per domain. The one-screen answer to 'where am I'."""
    positions = skill_positions(session, profile_id, as_of)
    ordered = session.scalars(select(SkillDomain).order_by(SkillDomain.ordinal))
    domains = {d.code: d for d in ordered}

    summary: list[dict[str, object]] = []
    for code, domain in domains.items():
        rows = [p for p in positions if p.domain_code == code]
        targeted = [p for p in rows if p.target_level > 0]
        summary.append(
            {
                "domain_code": code,
                "domain_name": domain.name,
                "skills": len(rows),
                "targeted": len(targeted),
                "at_target": sum(1 for p in targeted if p.gap == 0),
                "total_gap": sum(p.gap for p in targeted),
                "decayed": sum(1 for p in rows if p.is_decayed),
                "blocked": sum(1 for p in targeted if p.is_blocked and p.gap > 0),
            }
        )
    return summary
