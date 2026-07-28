"""Shared FastAPI dependencies.

Profile resolution lives here because every endpoint needs it and none should
reimplement it. The default is the demo profile: it makes `/docs` explorable
on a fresh install without anyone having to look up an identifier first, and
the demo profile is disposable by definition — `make demo` rebuilds it.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Profile


def get_profile(
    profile: str = Query(
        default="demo",
        description="Profile code. Defaults to the demonstration profile.",
    ),
    db: Session = Depends(get_db),
) -> Profile:
    found = db.scalar(select(Profile).where(Profile.code == profile))
    if found is None:
        known = [p.code for p in db.scalars(select(Profile))]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown profile '{profile}'. Known profiles: {', '.join(known) or 'none'}",
        )
    return found
