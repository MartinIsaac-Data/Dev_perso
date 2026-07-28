"""Deliverable engine: quotas, evidence, and the rule that governs promotion.

Two opinions are implemented here.

**Quotas are quarterly and reported per quarter, never as a running annual
total.** An annual target is satisfiable by a burst in December, and a system
that only reports the annual number would call that a success. Reporting each
quarter separately is what makes a silent quarter visible while there is still
time to act on it.

**A level rises only against a deliverable.** The database enforces that a
promotion carries a `deliverable_id`; this module enforces the rest of what
makes the claim honest — that the deliverable belongs to the same profile,
that it is actually published, and that it exercised the skill being claimed.
A constraint cannot express those; a service can, and every write path goes
through here.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Deliverable,
    DeliverableQuota,
    DeliverableSkill,
    DeliverableType,
    Phase,
    Skill,
    SkillLevelChange,
    SkillState,
)


class EvidenceError(ValueError):
    """Raised when a promotion is not supported by acceptable evidence."""


# --------------------------------------------------------------------------
# Calendar helpers
# --------------------------------------------------------------------------


def quarter_of(day: date) -> int:
    return (day.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    first_month = 3 * (quarter - 1) + 1
    start = date(year, first_month, 1)
    if quarter == 4:
        end = date(year, 12, 31)
    else:
        end = date(year, first_month + 3, 1).toordinal() - 1
        end = date.fromordinal(end)
    return start, end


def iter_quarters(start: date, end: date) -> Iterator[tuple[int, int]]:
    """Yield (year, quarter) from the quarter containing `start` to that of `end`."""
    year, quarter = start.year, quarter_of(start)
    last = (end.year, quarter_of(end))
    while (year, quarter) <= last:
        yield year, quarter
        quarter += 1
        if quarter == 5:
            quarter = 1
            year += 1


# --------------------------------------------------------------------------
# Quota compliance
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QuotaLine:
    type_code: str
    type_name: str
    required: int
    published: int

    @property
    def met(self) -> bool:
        return self.published >= self.required

    @property
    def shortfall(self) -> int:
        return max(0, self.required - self.published)


@dataclass(frozen=True)
class QuarterStatus:
    year: int
    quarter: int
    starts_on: date
    ends_on: date
    phase_code: str | None
    phase_name: str | None
    # True while the quarter is still running: a shortfall is not yet a miss.
    is_current: bool
    lines: list[QuotaLine] = field(default_factory=list)
    total_published: int = 0

    @property
    def met(self) -> bool:
        return all(line.met for line in self.lines)

    @property
    def is_silent(self) -> bool:
        """Nothing published at all. The signal that matters most."""
        return self.total_published == 0


def phase_for(session: Session, day: date) -> Phase | None:
    return session.scalar(
        select(Phase).where(Phase.starts_on <= day, Phase.ends_on >= day)
    )


def quota_status(
    session: Session,
    profile_id: int,
    as_of: date | None = None,
    quarters_back: int = 5,
) -> list[QuarterStatus]:
    """Per-quarter compliance, most recent last.

    `quarters_back` counts backwards from and including the current quarter,
    so the default reports a little over a year — long enough for a pattern to
    show, short enough to act on.
    """
    as_of = as_of or date.today()
    end_year, end_quarter = as_of.year, quarter_of(as_of)

    # Walk back to the first quarter to report.
    year, quarter = end_year, end_quarter
    for _ in range(max(0, quarters_back - 1)):
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    window_start, _ = quarter_bounds(year, quarter)

    published = list(
        session.scalars(
            select(Deliverable)
            .options(selectinload(Deliverable.type))
            .where(
                Deliverable.profile_id == profile_id,
                Deliverable.status == "published",
                Deliverable.published_on.isnot(None),
                Deliverable.published_on >= window_start,
            )
        )
    )

    statuses: list[QuarterStatus] = []
    for q_year, q_number in iter_quarters(window_start, as_of):
        starts_on, ends_on = quarter_bounds(q_year, q_number)
        phase = phase_for(session, starts_on)

        in_quarter = [
            d for d in published if starts_on <= d.published_on <= ends_on
        ]
        counts: dict[str, int] = {}
        for deliverable in in_quarter:
            counts[deliverable.type.code] = counts.get(deliverable.type.code, 0) + 1

        lines: list[QuotaLine] = []
        if phase is not None:
            quotas = session.scalars(
                select(DeliverableQuota)
                .options(selectinload(DeliverableQuota.deliverable_type))
                .where(
                    DeliverableQuota.phase_id == phase.id,
                    DeliverableQuota.min_per_quarter > 0,
                )
            )
            for quota in quotas:
                type_ = quota.deliverable_type
                lines.append(
                    QuotaLine(
                        type_code=type_.code,
                        type_name=type_.name,
                        required=quota.min_per_quarter,
                        published=counts.get(type_.code, 0),
                    )
                )
            lines.sort(key=lambda line: line.type_code)

        statuses.append(
            QuarterStatus(
                year=q_year,
                quarter=q_number,
                starts_on=starts_on,
                ends_on=ends_on,
                phase_code=phase.code if phase else None,
                phase_name=phase.name if phase else None,
                is_current=(q_year, q_number) == (end_year, end_quarter),
                lines=lines,
                total_published=len(in_quarter),
            )
        )
    return statuses


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    deliverable_id: int
    title: str
    type_code: str
    type_name: str
    published_on: date | None
    artifact_url: str | None
    # True when this deliverable was cited to justify a level change, as
    # opposed to merely having exercised the skill.
    cited_for_promotion: bool
    contribution: int | None


@dataclass(frozen=True)
class SkillEvidence:
    skill_code: str
    skill_name: str
    domain_name: str
    current_level: int
    evidence: list[EvidenceItem] = field(default_factory=list)

    @property
    def is_defensible(self) -> bool:
        """Level 3 or above with at least one published artefact behind it.

        The question an interviewer actually asks. A level claimed with no
        evidence is not a lie, but it is not defensible either, and the
        distinction is worth surfacing before somebody else makes it.
        """
        return self.current_level < 3 or any(e.published_on for e in self.evidence)


def evidence_cv(
    session: Session, profile_id: int, min_level: int = 2
) -> list[SkillEvidence]:
    """What can be claimed, and what backs each claim.

    Ordered by level then by code. This is the raw material for a CV: every
    line is a skill with the artefacts that justify it, so nothing appears
    that cannot be pointed at.
    """
    states = list(
        session.scalars(
            select(SkillState)
            .options(selectinload(SkillState.skill).selectinload(Skill.domain))
            .where(
                SkillState.profile_id == profile_id,
                SkillState.current_level >= min_level,
            )
        )
    )

    promotions = list(
        session.scalars(
            select(SkillLevelChange).where(
                SkillLevelChange.profile_id == profile_id,
                SkillLevelChange.deliverable_id.isnot(None),
            )
        )
    )
    cited: dict[int, set[int]] = {}
    for change in promotions:
        cited.setdefault(change.skill_id, set()).add(change.deliverable_id)

    links = list(
        session.scalars(
            select(DeliverableSkill)
            .options(
                selectinload(DeliverableSkill.deliverable).selectinload(Deliverable.type)
            )
            .join(Deliverable)
            .where(Deliverable.profile_id == profile_id)
        )
    )
    by_skill: dict[int, list[DeliverableSkill]] = {}
    for link in links:
        by_skill.setdefault(link.skill_id, []).append(link)

    result: list[SkillEvidence] = []
    for state in states:
        items: dict[int, EvidenceItem] = {}
        for link in by_skill.get(state.skill_id, []):
            deliverable = link.deliverable
            items[deliverable.id] = EvidenceItem(
                deliverable_id=deliverable.id,
                title=deliverable.title,
                type_code=deliverable.type.code,
                type_name=deliverable.type.name,
                published_on=deliverable.published_on,
                artifact_url=deliverable.artifact_url,
                cited_for_promotion=deliverable.id in cited.get(state.skill_id, set()),
                contribution=link.contribution,
            )
        # A deliverable can be cited as evidence without being linked as a
        # skill contributor; include it rather than lose the citation.
        for deliverable_id in cited.get(state.skill_id, set()):
            if deliverable_id in items:
                continue
            deliverable = session.get(Deliverable, deliverable_id)
            if deliverable is None:
                continue
            items[deliverable_id] = EvidenceItem(
                deliverable_id=deliverable.id,
                title=deliverable.title,
                type_code=deliverable.type.code,
                type_name=deliverable.type.name,
                published_on=deliverable.published_on,
                artifact_url=deliverable.artifact_url,
                cited_for_promotion=True,
                contribution=None,
            )

        result.append(
            SkillEvidence(
                skill_code=state.skill.code,
                skill_name=state.skill.name,
                domain_name=state.skill.domain.name,
                current_level=state.current_level,
                evidence=sorted(
                    items.values(),
                    key=lambda e: (e.published_on or date.min, e.title),
                    reverse=True,
                ),
            )
        )

    result.sort(key=lambda s: (-s.current_level, s.skill_code))
    return result


# --------------------------------------------------------------------------
# Promotion
# --------------------------------------------------------------------------


def record_level_change(
    session: Session,
    *,
    profile_id: int,
    skill_id: int,
    to_level: int,
    changed_on: date | None = None,
    deliverable_id: int | None = None,
    rationale: str | None = None,
) -> SkillLevelChange:
    """Move a skill's level, appending to the audit trail.

    The database guarantees a promotion carries a deliverable. This function
    guarantees the three things a CHECK constraint cannot see: that the
    deliverable belongs to this profile, that it is published, and that it is
    linked to the skill being claimed. Without those, the evidence rule is
    satisfiable by pointing at any row in the table.
    """
    changed_on = changed_on or date.today()
    if not 0 <= to_level <= 5:
        raise EvidenceError(f"level must be between 0 and 5, got {to_level}")

    state = session.scalar(
        select(SkillState).where(
            SkillState.profile_id == profile_id, SkillState.skill_id == skill_id
        )
    )
    from_level = state.current_level if state else 0

    if to_level > from_level:
        if deliverable_id is None:
            raise EvidenceError(
                "a level only rises against evidence: supply a published deliverable"
            )
        deliverable = session.get(Deliverable, deliverable_id)
        if deliverable is None:
            raise EvidenceError(f"deliverable {deliverable_id} does not exist")
        if deliverable.profile_id != profile_id:
            raise EvidenceError("the evidence belongs to a different profile")
        if deliverable.status != "published":
            raise EvidenceError(
                f"evidence must be published; '{deliverable.title}' is {deliverable.status}"
            )
        linked = session.scalar(
            select(DeliverableSkill).where(
                DeliverableSkill.deliverable_id == deliverable_id,
                DeliverableSkill.skill_id == skill_id,
            )
        )
        if linked is None:
            raise EvidenceError(
                "the evidence does not exercise this skill: link the deliverable "
                "to the skill first, or cite a different one"
            )

    change = SkillLevelChange(
        profile_id=profile_id,
        skill_id=skill_id,
        from_level=from_level,
        to_level=to_level,
        changed_on=changed_on,
        deliverable_id=deliverable_id if to_level > from_level else None,
        rationale=rationale,
    )
    session.add(change)

    if state is None:
        state = SkillState(
            profile_id=profile_id,
            skill_id=skill_id,
            current_level=to_level,
            target_level=max(to_level, 3),
        )
        session.add(state)
    else:
        state.current_level = to_level

    if to_level > from_level:
        # `last_practised_on` is denormalised from evidence and maintained
        # here only — never edited by hand.
        practised = None
        if deliverable_id is not None:
            deliverable = session.get(Deliverable, deliverable_id)
            practised = deliverable.published_on if deliverable else None
        candidate = practised or changed_on
        if state.last_practised_on is None or candidate > state.last_practised_on:
            state.last_practised_on = candidate

    session.flush()
    return change


def touch_skills_from_deliverable(session: Session, deliverable: Deliverable) -> int:
    """Refresh `last_practised_on` for every skill a published deliverable used.

    Called when a deliverable is published. Publishing an article that
    exercised DAX is practice, whether or not it justifies a promotion, and
    the decay clock should reflect that.
    """
    if deliverable.status != "published" or deliverable.published_on is None:
        return 0

    links = list(
        session.scalars(
            select(DeliverableSkill).where(
                DeliverableSkill.deliverable_id == deliverable.id
            )
        )
    )
    updated = 0
    for link in links:
        state = session.scalar(
            select(SkillState).where(
                SkillState.profile_id == deliverable.profile_id,
                SkillState.skill_id == link.skill_id,
            )
        )
        if state is None:
            continue
        if state.last_practised_on is None or deliverable.published_on > state.last_practised_on:
            state.last_practised_on = deliverable.published_on
            updated += 1
    session.flush()
    return updated


def available_deliverable_types(session: Session) -> list[DeliverableType]:
    return list(session.scalars(select(DeliverableType).order_by(DeliverableType.code)))
