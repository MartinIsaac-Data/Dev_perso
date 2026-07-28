"""Job posting extraction.

The raw advert text is stored in full alongside the extracted requirements,
and the extraction points at the `agent_run` that produced it. When the prompt
improves in 2028, the 2026 corpus can be re-processed and the two extractions
compared, rather than the older one being the only one that ever existed.

A skill code the agent invents is not written to `skill_id`. It is kept in
`raw_label` and left unmapped, which puts it in the same bucket as a genuine
requirement the taxonomy cannot express — and that bucket is the one worth
reading.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobPosting, JobRequirement, Skill, TargetRole
from app.models.base import IMPORTANCE
from app.services.agents.client import LlmClient
from app.services.agents.runner import run_agent


class RequirementOut(BaseModel):
    raw_label: str = Field(description="The employer's own words.")
    skill_code: str | None = Field(
        default=None,
        description="Taxonomy code, or null when nothing in the taxonomy "
        "genuinely covers this requirement. Null is a valid and valuable answer.",
    )
    required_level: int | None = Field(default=None, ge=0, le=5)
    importance: str = Field(default="must_have", description="must_have or nice_to_have")
    evidence_quote: str | None = Field(
        default=None, description="Shortest exact span of the advert supporting this."
    )


class PostingExtractionOutput(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    seniority_label: str | None = None
    requirements: list[RequirementOut]
    extraction_note: str | None = None


def build_posting_context(raw_text: str, skills: list[Skill]) -> dict[str, Any]:
    """The advert plus the taxonomy the agent may map onto.

    The full taxonomy is supplied every time rather than a shortlist chosen by
    keyword. A shortlist would decide the mapping before the agent saw the
    text, and would make an unmapped requirement indistinguishable from one
    whose code simply was not offered.
    """
    return {
        "posting_text": raw_text,
        "taxonomy": [
            {"code": skill.code, "name": skill.name, "domain": skill.domain.code}
            for skill in sorted(skills, key=lambda s: s.code)
        ],
        "level_scale": {
            "2": "exposure expected",
            "3": "works unaided — the default when a skill is simply listed",
            "4": "designs with it, leads, owns the approach",
            "5": "recognised authority",
        },
    }


def extract_posting(
    session: Session,
    raw_text: str,
    client: LlmClient,
    *,
    target_role_code: str | None = None,
    source: str | None = None,
    url: str | None = None,
    posted_on: date | None = None,
    captured_on: date | None = None,
    model_name: str | None = None,
) -> JobPosting:
    skills = list(session.scalars(select(Skill)))
    by_code = {skill.code: skill for skill in skills}

    run, output = run_agent(
        session,
        agent_name="posting_extraction",
        prompt_name="posting_extraction",
        payload=build_posting_context(raw_text, skills),
        output_model=PostingExtractionOutput,
        client=client,
        model=model_name,
    )

    role = None
    if target_role_code:
        role = session.scalar(select(TargetRole).where(TargetRole.code == target_role_code))

    posting = JobPosting(
        target_role_id=role.id if role else None,
        title=output.title,
        company=output.company,
        location=output.location,
        seniority_label=output.seniority_label,
        source=source,
        url=url,
        posted_on=posted_on,
        captured_on=captured_on or date.today(),
        raw_text=raw_text,
    )
    session.add(posting)
    session.flush()

    seen: set[str] = set()
    for requirement in output.requirements:
        # The unique constraint is on (posting, raw_label, agent_run); two
        # identical labels in one extraction would violate it, and the second
        # carries no information.
        if requirement.raw_label in seen:
            continue
        seen.add(requirement.raw_label)

        skill = by_code.get(requirement.skill_code or "")
        session.add(
            JobRequirement(
                posting_id=posting.id,
                agent_run_id=run.id,
                raw_label=requirement.raw_label,
                skill_id=skill.id if skill else None,
                required_level=requirement.required_level,
                importance=(
                    requirement.importance
                    if requirement.importance in IMPORTANCE
                    else "must_have"
                ),
                evidence_quote=requirement.evidence_quote,
            )
        )

    session.flush()
    return posting
