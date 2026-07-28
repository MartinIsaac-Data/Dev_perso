"""Deliverable, quota and evidence endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_profile
from app.db import get_db
from app.models import (
    Deliverable,
    DeliverableSkill,
    DeliverableType,
    Profile,
    Skill,
)
from app.schemas.deliverable import (
    DeliverableIn,
    DeliverableOut,
    DeliverableSkillOut,
    DeliverableTypeOut,
    DeliverableUpdateIn,
    QuarterStatusOut,
    SkillEvidenceOut,
)
from app.services import deliverables as service

router = APIRouter(tags=["deliverables"])


def _to_out(deliverable: Deliverable) -> DeliverableOut:
    return DeliverableOut(
        id=deliverable.id,
        title=deliverable.title,
        summary=deliverable.summary,
        type_code=deliverable.type.code,
        type_name=deliverable.type.name,
        status=deliverable.status,
        started_on=deliverable.started_on,
        published_on=deliverable.published_on,
        artifact_url=deliverable.artifact_url,
        business_value=deliverable.business_value,
        skills=[
            DeliverableSkillOut(
                skill_id=link.skill_id,
                skill_code=link.skill.code,
                skill_name=link.skill.name,
                contribution=link.contribution,
            )
            for link in sorted(deliverable.skills, key=lambda x: -x.contribution)
        ],
        impacts=list(deliverable.impacts),
    )


def _load(db: Session, deliverable_id: int, profile: Profile) -> Deliverable:
    deliverable = db.scalar(
        select(Deliverable)
        .options(
            selectinload(Deliverable.type),
            selectinload(Deliverable.skills).selectinload(DeliverableSkill.skill),
            selectinload(Deliverable.impacts),
        )
        .where(Deliverable.id == deliverable_id)
    )
    if deliverable is None or deliverable.profile_id != profile.id:
        # Same response whether it does not exist or belongs to another
        # profile: nothing useful is gained by distinguishing them.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deliverable not found")
    return deliverable


def _apply_skills(
    db: Session, deliverable: Deliverable, links: list, replace: bool
) -> None:
    """Set the skill links, going through the relationship rather than the table.

    Deleting `DeliverableSkill` rows directly would leave `deliverable.skills`
    holding the removed objects in memory. Sessions here are created with
    `expire_on_commit=False`, so that stale collection survives the commit and
    is what the response is serialised from — the write succeeds and the
    caller is told it did not happen. Mutating the collection keeps the
    in-memory object and the database in step.
    """
    codes = {link.skill_code for link in links}
    found = {s.code: s for s in db.scalars(select(Skill).where(Skill.code.in_(codes)))}
    unknown = sorted(codes - set(found))
    if unknown:
        raise HTTPException(422, f"unknown skill codes: {', '.join(unknown)}")

    if replace:
        # delete-orphan on the relationship issues the DELETEs.
        deliverable.skills.clear()
        db.flush()

    for link in links:
        deliverable.skills.append(
            DeliverableSkill(
                skill_id=found[link.skill_code].id,
                contribution=link.contribution,
            )
        )
    db.flush()


@router.get("/deliverable-types", response_model=list[DeliverableTypeOut])
def list_types(db: Session = Depends(get_db)) -> list[DeliverableType]:
    return service.available_deliverable_types(db)


@router.get("/deliverables", response_model=list[DeliverableOut])
def list_deliverables(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    type_code: str | None = Query(default=None),
) -> list[DeliverableOut]:
    """Newest first, with unpublished work last — it has no date to sort on."""
    query = (
        select(Deliverable)
        .options(
            selectinload(Deliverable.type),
            selectinload(Deliverable.skills).selectinload(DeliverableSkill.skill),
            selectinload(Deliverable.impacts),
        )
        .where(Deliverable.profile_id == profile.id)
    )
    if status_filter:
        query = query.where(Deliverable.status == status_filter)
    if type_code:
        query = query.join(DeliverableType).where(DeliverableType.code == type_code)

    rows = list(db.scalars(query))
    rows.sort(key=lambda d: (d.published_on is None, d.published_on or date.min), reverse=True)
    return [_to_out(d) for d in rows]


@router.post(
    "/deliverables", response_model=DeliverableOut, status_code=status.HTTP_201_CREATED
)
def create_deliverable(
    payload: DeliverableIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> DeliverableOut:
    type_ = db.scalar(select(DeliverableType).where(DeliverableType.code == payload.type_code))
    if type_ is None:
        raise HTTPException(
            422,
            f"unknown deliverable type '{payload.type_code}'",
        )

    deliverable = Deliverable(
        profile_id=profile.id,
        type_id=type_.id,
        title=payload.title,
        summary=payload.summary,
        status=payload.status,
        started_on=payload.started_on,
        published_on=payload.published_on,
        artifact_url=payload.artifact_url,
        business_value=payload.business_value,
    )
    db.add(deliverable)
    db.flush()
    _apply_skills(db, deliverable, payload.skills, replace=False)
    db.flush()
    # Publishing counts as practice for every skill exercised, whether or not
    # it justifies a promotion.
    service.touch_skills_from_deliverable(db, deliverable)
    db.commit()
    return _to_out(_load(db, deliverable.id, profile))


@router.get("/deliverables/{deliverable_id}", response_model=DeliverableOut)
def get_deliverable(
    deliverable_id: int,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> DeliverableOut:
    return _to_out(_load(db, deliverable_id, profile))


@router.patch("/deliverables/{deliverable_id}", response_model=DeliverableOut)
def update_deliverable(
    deliverable_id: int,
    payload: DeliverableUpdateIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> DeliverableOut:
    deliverable = _load(db, deliverable_id, profile)
    data = payload.model_dump(exclude_unset=True)
    skills = data.pop("skills", None)

    for field_name, value in data.items():
        setattr(deliverable, field_name, value)

    if deliverable.status == "published" and deliverable.published_on is None:
        raise HTTPException(
            422,
            "a published deliverable needs a published_on date",
        )

    if skills is not None:
        _apply_skills(db, deliverable, payload.skills or [], replace=True)

    db.flush()
    service.touch_skills_from_deliverable(db, deliverable)
    db.commit()
    return _to_out(_load(db, deliverable_id, profile))


@router.delete("/deliverables/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deliverable(
    deliverable_id: int,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> None:
    deliverable = _load(db, deliverable_id, profile)
    db.delete(deliverable)
    try:
        db.commit()
    except Exception as exc:  # IntegrityError from the RESTRICT on evidence
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "this deliverable is cited as evidence for a level change; "
            "withdraw the level change first",
        ) from exc


@router.get("/quota-status", response_model=list[QuarterStatusOut], tags=["quotas"])
def get_quota_status(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    as_of: date | None = Query(default=None, description="Defaults to today."),
    quarters_back: int = Query(default=5, ge=1, le=40),
) -> list[service.QuarterStatus]:
    """Per-quarter quota compliance, oldest first.

    Reported quarter by quarter rather than as a running annual total: an
    annual target is satisfiable by a burst in December, and this is the view
    that makes a silent quarter visible while it can still be acted on.
    """
    return service.quota_status(db, profile.id, as_of, quarters_back)


@router.get("/evidence-cv", response_model=list[SkillEvidenceOut], tags=["evidence"])
def get_evidence_cv(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    min_level: int = Query(default=2, ge=0, le=5),
) -> list[service.SkillEvidence]:
    """Every claimable skill with the artefacts that justify it.

    `is_defensible` is false for a skill at level 3 or above with nothing
    published behind it — the gap an interviewer finds before you do.
    """
    return service.evidence_cv(db, profile.id, min_level)
