"""Skill graph endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_profile
from app.db import get_db
from app.models import Profile, Skill, SkillDomain, SkillEdge, SkillLevel, SkillState
from app.schemas.skill import (
    DomainSummaryOut,
    GraphOut,
    LevelChangeIn,
    LevelChangeOut,
    SkillLevelOut,
    SkillPositionOut,
    SkillStateUpsertIn,
)
from app.services import skill_graph
from app.services.deliverables import EvidenceError, record_level_change
from app.services.graph import find_cycle, topological_order

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/levels", response_model=list[SkillLevelOut])
def list_levels(db: Session = Depends(get_db)) -> list[SkillLevel]:
    """The 0-5 scale and what each level actually requires as evidence."""
    return list(db.scalars(select(SkillLevel).order_by(SkillLevel.level)))


@router.get("/graph", response_model=GraphOut)
def get_graph(db: Session = Depends(get_db)) -> GraphOut:
    """The taxonomy: nodes, edges and its shape. Profile-independent."""
    domains = list(db.scalars(select(SkillDomain).order_by(SkillDomain.ordinal)))
    skills = list(db.scalars(select(Skill).order_by(Skill.code)))
    edges = list(db.scalars(select(SkillEdge)))
    pairs = [(e.prerequisite_skill_id, e.dependent_skill_id) for e in edges]

    cycle = find_cycle(pairs)
    longest = 0
    if cycle is None:
        order = topological_order(pairs, nodes=[s.id for s in skills])
        depth = dict.fromkeys(order, 1)
        successors: dict[int, list[int]] = {}
        for a, b in pairs:
            successors.setdefault(a, []).append(b)
        for node in order:
            for nxt in successors.get(node, []):
                depth[nxt] = max(depth.get(nxt, 1), depth[node] + 1)
        longest = max(depth.values()) if depth else 0

    return GraphOut(
        domains=domains,
        skills=skills,
        edges=edges,
        is_acyclic=cycle is None,
        longest_chain=longest,
    )


@router.get("/positions", response_model=list[SkillPositionOut])
def list_positions(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = Query(default=None, description="Defaults to today."),
    domain: str | None = Query(default=None, description="Filter by domain code."),
    tracked_only: bool = Query(default=False),
) -> list[skill_graph.SkillPosition]:
    """Every skill, with this profile's position on it."""
    positions = skill_graph.skill_positions(db, profile.id, as_of)
    if domain:
        positions = [p for p in positions if p.domain_code == domain]
    if tracked_only:
        positions = [p for p in positions if p.tracked]
    return positions


@router.get("/critical-path", response_model=list[SkillPositionOut])
def get_critical_path(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
    as_of: date | None = None,
) -> list[skill_graph.SkillPosition]:
    """Skills below target, ranked by how many other wanted skills they gate.

    Not a ranking of the taxonomy: a prerequisite whose dependents are already
    satisfied scores zero here, however central it looks in the graph.
    """
    return skill_graph.critical_path(db, profile.id, limit, as_of)


@router.get("/available", response_model=list[SkillPositionOut])
def get_available(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = None,
) -> list[skill_graph.SkillPosition]:
    """Below target with every prerequisite satisfied — startable today."""
    return skill_graph.available_now(db, profile.id, as_of)


@router.get("/blocked", response_model=list[SkillPositionOut])
def get_blocked(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = None,
) -> list[skill_graph.SkillPosition]:
    """Below target and gated, with the specific unmet prerequisites named."""
    return skill_graph.blocked_skills(db, profile.id, as_of)


@router.get("/decayed", response_model=list[SkillPositionOut])
def get_decayed(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = None,
) -> list[skill_graph.SkillPosition]:
    """Skills past their decay window, worst overrun first.

    Includes skills already at target: one sitting at its target untouched for
    eighteen months is the one nobody thinks to check.
    """
    return skill_graph.decayed_skills(db, profile.id, as_of)


@router.get("/learning-order", response_model=list[str])
def get_learning_order(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = None,
) -> list[str]:
    """Skill codes still below target, ordered so nothing precedes its prerequisites."""
    return skill_graph.learning_order(db, profile.id, as_of)


@router.get("/domains/summary", response_model=list[DomainSummaryOut])
def get_domain_summary(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = None,
) -> list[dict[str, object]]:
    return skill_graph.domain_summary(db, profile.id, as_of)


@router.put("/{code}/target", response_model=SkillPositionOut)
def set_target(
    code: str,
    payload: SkillStateUpsertIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> skill_graph.SkillPosition:
    """Set the target level for a skill, creating the state row if needed.

    Cannot change `current_level` — that is what the evidence rule governs,
    and it lives on /skills/{code}/level.
    """
    skill = db.scalar(select(Skill).where(Skill.code == code))
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown skill '{code}'")

    state = db.scalar(
        select(SkillState).where(
            SkillState.profile_id == profile.id, SkillState.skill_id == skill.id
        )
    )
    if state is None:
        state = SkillState(
            profile_id=profile.id,
            skill_id=skill.id,
            current_level=0,
            target_level=payload.target_level,
            notes=payload.notes,
        )
        db.add(state)
    else:
        state.target_level = payload.target_level
        if payload.notes is not None:
            state.notes = payload.notes
    db.commit()

    positions = {p.code: p for p in skill_graph.skill_positions(db, profile.id)}
    return positions[code]


@router.post(
    "/{code}/level",
    response_model=LevelChangeOut,
    status_code=status.HTTP_201_CREATED,
)
def change_level(
    code: str,
    payload: LevelChangeIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> LevelChangeOut:
    """Record a level change.

    Raising a level requires a published deliverable of this profile that is
    linked to this skill. Lowering one requires nothing: admitting decay must
    never cost paperwork, or it will simply go unrecorded.
    """
    skill = db.scalar(select(Skill).where(Skill.code == code))
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown skill '{code}'")

    try:
        change = record_level_change(
            db,
            profile_id=profile.id,
            skill_id=skill.id,
            to_level=payload.to_level,
            changed_on=payload.changed_on,
            deliverable_id=payload.deliverable_id,
            rationale=payload.rationale,
        )
    except EvidenceError as exc:
        # 422 rather than 400: the request is well formed, but the state of
        # the world does not support the claim it makes.
        raise HTTPException(422, str(exc)) from exc

    db.commit()
    return LevelChangeOut.model_validate(change)
