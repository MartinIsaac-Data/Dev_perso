"""FastAPI application.

Phase 0 exposes only what is needed to prove the stack is wired end to end:
health, and a metadata endpoint that reports what the database actually
contains. The domain routers arrive in Phase 1.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Deliverable, Profile, Skill, SkillEdge

app = FastAPI(
    title="Transformation OS",
    version="0.1.0",
    description=(
        "Local-first system for steering a data and AI transformation career: "
        "skill graph, deliverable engine, business case lab, market gap radar."
    ),
)

# The front end runs on a different port in development. Restricted to
# localhost origins because this application is local-first by design and
# should never be reachable from anywhere else without a deliberate change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta", tags=["meta"])
def meta(db: Session = Depends(get_db)) -> dict[str, object]:
    """What is actually loaded. The first thing to check after a fresh setup."""
    settings = get_settings()
    profiles = list(db.scalars(select(Profile)))
    return {
        "version": app.version,
        "backend": "sqlite" if settings.is_sqlite else "postgresql",
        "agents_configured": settings.anthropic_api_key is not None,
        "counts": {
            "skills": db.scalar(select(func.count()).select_from(Skill)),
            "skill_edges": db.scalar(select(func.count()).select_from(SkillEdge)),
            "deliverables": db.scalar(select(func.count()).select_from(Deliverable)),
        },
        "profiles": [
            {"code": p.code, "display_name": p.display_name, "is_demo": p.is_demo}
            for p in profiles
        ],
    }
