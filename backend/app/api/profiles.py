"""Profile and trajectory endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import DeliverableQuota, Phase, Profile, TargetRole
from app.services.deliverables import phase_for

router = APIRouter(tags=["profiles"])


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    display_name: str
    is_demo: bool
    based_in: str | None = None
    currency: str


class QuotaOut(BaseModel):
    type_code: str
    type_name: str
    min_per_quarter: int


class PhaseOut(BaseModel):
    code: str
    name: str
    ordinal: int
    starts_on: date
    ends_on: date
    objective: str | None = None
    is_current: bool
    quotas: list[QuotaOut] = []


class TargetRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str | None = None


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)) -> list[Profile]:
    return list(db.scalars(select(Profile).order_by(Profile.code)))


@router.get("/phases", response_model=list[PhaseOut])
def list_phases(db: Session = Depends(get_db)) -> list[PhaseOut]:
    """The trajectory and its quarterly quotas."""
    today = date.today()
    current = phase_for(db, today)
    phases = list(
        db.scalars(
            select(Phase)
            .options(
                selectinload(Phase.quotas).selectinload(DeliverableQuota.deliverable_type)
            )
            .order_by(Phase.ordinal)
        )
    )
    return [
        PhaseOut(
            code=phase.code,
            name=phase.name,
            ordinal=phase.ordinal,
            starts_on=phase.starts_on,
            ends_on=phase.ends_on,
            objective=phase.objective,
            is_current=current is not None and current.id == phase.id,
            quotas=[
                QuotaOut(
                    type_code=quota.deliverable_type.code,
                    type_name=quota.deliverable_type.name,
                    min_per_quarter=quota.min_per_quarter,
                )
                for quota in sorted(
                    phase.quotas, key=lambda q: q.deliverable_type.code
                )
            ],
        )
        for phase in phases
    ]


@router.get("/target-roles", response_model=list[TargetRoleOut])
def list_target_roles(db: Session = Depends(get_db)) -> list[TargetRole]:
    return list(db.scalars(select(TargetRole).order_by(TargetRole.code)))
