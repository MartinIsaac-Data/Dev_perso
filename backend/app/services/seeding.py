"""Seed loading.

Two seeds, with different rules, and the difference matters:

**Reference seed** (skill taxonomy, levels, deliverable types, phases, review
criteria) is *upserted by code* and is safe to re-run at any time, including
against a database holding real data. Adding a skill to the taxonomy in 2029
must not require dropping anything.

**Demo seed** is *destructive within its own profile*: it deletes the demo
profile and everything hanging off it, then rebuilds. It never touches any
other profile. This is what makes the application demonstrable in an interview
without a second database or a sanitising export — the demo data and the real
data live side by side, separated by a foreign key.

The DAG is validated before any edge is written. A taxonomy with a cycle is
not a taxonomy with a small bug; every downstream query — critical path,
learning order, blocked-skill detection — becomes meaningless, so it is
rejected at the door.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Assumption,
    BusinessCase,
    CaseReview,
    CaseReviewChallenge,
    CaseReviewScore,
    CauseDriver,
    CauseNode,
    Deliverable,
    DeliverableImpact,
    DeliverableQuota,
    DeliverableSkill,
    DeliverableType,
    JobPosting,
    JobRequirement,
    Mention,
    PeriodicReview,
    Phase,
    Profile,
    ReviewCriterion,
    RoiLine,
    RoiModel,
    Skill,
    SkillDomain,
    SkillEdge,
    SkillLevel,
    SkillLevelChange,
    SkillState,
    Solution,
    SolutionKpi,
    TargetRole,
)
from app.services.graph import assert_acyclic


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _dec(value: Any) -> Decimal | None:
    """YAML gives floats; money must not be one. Round-trip through str."""
    if value is None:
        return None
    return Decimal(str(value))


def _upsert(session: Session, model: type, code: str, **fields: Any) -> Any:
    """Insert or update a reference row identified by its `code`."""
    obj = session.scalar(select(model).where(model.code == code))
    if obj is None:
        obj = model(code=code, **fields)
        session.add(obj)
    else:
        for key, value in fields.items():
            setattr(obj, key, value)
    return obj


# --------------------------------------------------------------------------
# Reference seed
# --------------------------------------------------------------------------


def seed_reference(session: Session, seeds_dir: Path | None = None) -> dict[str, int]:
    seeds_dir = seeds_dir or get_settings().seeds_dir
    ref = seeds_dir / "reference"
    counts: dict[str, int] = {}

    # --- Skill levels (natural primary key: the level itself) --------------
    levels = _load_yaml(ref / "skill_levels.yaml")["skill_levels"]
    for row in levels:
        existing = session.get(SkillLevel, row["level"])
        payload = {
            "code": row["code"],
            "name": row["name"],
            "definition": row["definition"].strip(),
            "evidence_expectation": (row.get("evidence_expectation") or "").strip() or None,
        }
        if existing is None:
            session.add(SkillLevel(level=row["level"], **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    counts["skill_levels"] = len(levels)

    # --- Deliverable types --------------------------------------------------
    types = _load_yaml(ref / "deliverable_types.yaml")["deliverable_types"]
    for row in types:
        _upsert(
            session,
            DeliverableType,
            row["code"],
            name=row["name"],
            is_publication=bool(row.get("is_publication", False)),
            description=(row.get("description") or "").strip() or None,
        )
    counts["deliverable_types"] = len(types)

    # --- Review criteria ----------------------------------------------------
    criteria = _load_yaml(ref / "review_criteria.yaml")["review_criteria"]
    total_weight = sum(Decimal(str(c["weight"])) for c in criteria)
    if total_weight != Decimal("1"):
        raise ValueError(
            f"review criterion weights must sum to exactly 1, got {total_weight}"
        )
    for row in criteria:
        _upsert(
            session,
            ReviewCriterion,
            row["code"],
            name=row["name"],
            definition=row["definition"].strip(),
            weight=_dec(row["weight"]),
            ordinal=row.get("ordinal", 0),
        )
    counts["review_criteria"] = len(criteria)

    # --- Target roles and phases -------------------------------------------
    trajectory = _load_yaml(ref / "phases.yaml")
    for row in trajectory["target_roles"]:
        _upsert(
            session,
            TargetRole,
            row["code"],
            name=row["name"],
            description=(row.get("description") or "").strip() or None,
        )
    counts["target_roles"] = len(trajectory["target_roles"])

    session.flush()
    type_by_code = {t.code: t for t in session.scalars(select(DeliverableType))}

    for row in trajectory["phases"]:
        phase = _upsert(
            session,
            Phase,
            row["code"],
            name=row["name"],
            ordinal=row["ordinal"],
            starts_on=row["starts_on"],
            ends_on=row["ends_on"],
            objective=(row.get("objective") or "").strip() or None,
        )
        session.flush()
        # Quotas are replaced wholesale: they are a property of the phase
        # definition, not accumulated state.
        session.execute(delete(DeliverableQuota).where(DeliverableQuota.phase_id == phase.id))
        for quota in row.get("quotas", []):
            session.add(
                DeliverableQuota(
                    phase_id=phase.id,
                    deliverable_type_id=type_by_code[quota["type"]].id,
                    min_per_quarter=quota["min_per_quarter"],
                )
            )
    counts["phases"] = len(trajectory["phases"])

    # --- Skill graph --------------------------------------------------------
    taxonomy = _load_yaml(ref / "skills.yaml")

    for row in taxonomy["domains"]:
        _upsert(session, SkillDomain, row["code"], name=row["name"], ordinal=row["ordinal"])
    session.flush()
    domain_by_code = {d.code: d for d in session.scalars(select(SkillDomain))}

    declared = {s["code"] for s in taxonomy["skills"]}
    for row in taxonomy["skills"]:
        _upsert(
            session,
            Skill,
            row["code"],
            name=row["name"],
            domain_id=domain_by_code[row["domain"]].id,
            description=(row.get("description") or "").strip() or None,
            decay_months=row.get("decay_months"),
        )
    counts["skills"] = len(taxonomy["skills"])

    edges = taxonomy.get("edges", [])
    unknown = {
        code
        for edge in edges
        for code in (edge["from"], edge["to"])
        if code not in declared
    }
    if unknown:
        raise ValueError(f"edges reference undeclared skills: {sorted(unknown)}")

    # Reject the whole taxonomy rather than write a cyclic graph.
    assert_acyclic([(e["from"], e["to"]) for e in edges])

    session.flush()
    skill_by_code = {s.code: s for s in session.scalars(select(Skill))}
    existing_edges = {
        (e.prerequisite_skill_id, e.dependent_skill_id): e
        for e in session.scalars(select(SkillEdge))
    }
    seen: set[tuple[int, int]] = set()
    for edge in edges:
        key = (skill_by_code[edge["from"]].id, skill_by_code[edge["to"]].id)
        seen.add(key)
        if key in existing_edges:
            existing_edges[key].required_level = edge.get("required_level", 3)
        else:
            session.add(
                SkillEdge(
                    prerequisite_skill_id=key[0],
                    dependent_skill_id=key[1],
                    required_level=edge.get("required_level", 3),
                    note=edge.get("note"),
                )
            )
    # Edges removed from the YAML are removed from the database, so the file
    # stays the single source of truth for the graph's shape.
    for key, obj in existing_edges.items():
        if key not in seen:
            session.delete(obj)
    counts["skill_edges"] = len(edges)

    return counts


# --------------------------------------------------------------------------
# Demo seed
# --------------------------------------------------------------------------


def reset_profile_data(session: Session, profile: Profile) -> None:
    """Delete everything owned by one profile, in dependency order.

    Explicit ordered deletes rather than relying on ON DELETE CASCADE: the
    evidence link `skill_level_change.deliverable_id` is RESTRICT on purpose,
    so a cascade from `profile` would hit that constraint depending on the
    order the backend happens to choose. Being explicit makes the teardown
    deterministic on SQLite and Postgres alike.
    """
    case_ids = list(
        session.scalars(select(BusinessCase.id).where(BusinessCase.profile_id == profile.id))
    )
    if case_ids:
        review_ids = list(
            session.scalars(select(CaseReview.id).where(CaseReview.case_id.in_(case_ids)))
        )
        if review_ids:
            session.execute(
                delete(CaseReviewChallenge).where(CaseReviewChallenge.review_id.in_(review_ids))
            )
            session.execute(
                delete(CaseReviewScore).where(CaseReviewScore.review_id.in_(review_ids))
            )
            session.execute(delete(CaseReview).where(CaseReview.id.in_(review_ids)))

        solution_ids = list(
            session.scalars(select(Solution.id).where(Solution.case_id.in_(case_ids)))
        )
        if solution_ids:
            session.execute(delete(SolutionKpi).where(SolutionKpi.solution_id.in_(solution_ids)))
            session.execute(delete(Solution).where(Solution.id.in_(solution_ids)))

        model_ids = list(
            session.scalars(select(RoiModel.id).where(RoiModel.case_id.in_(case_ids)))
        )
        if model_ids:
            session.execute(delete(RoiLine).where(RoiLine.roi_model_id.in_(model_ids)))
            session.execute(delete(RoiModel).where(RoiModel.id.in_(model_ids)))

        node_ids = list(
            session.scalars(select(CauseNode.id).where(CauseNode.case_id.in_(case_ids)))
        )
        if node_ids:
            session.execute(delete(CauseDriver).where(CauseDriver.cause_node_id.in_(node_ids)))
            # Children before parents: the self-referencing FK has no
            # deferred mode on SQLite.
            session.execute(
                delete(CauseNode).where(
                    CauseNode.id.in_(node_ids), CauseNode.parent_id.isnot(None)
                )
            )
            session.execute(delete(CauseNode).where(CauseNode.id.in_(node_ids)))

        session.execute(delete(Assumption).where(Assumption.case_id.in_(case_ids)))
        session.execute(delete(BusinessCase).where(BusinessCase.id.in_(case_ids)))

    session.execute(delete(PeriodicReview).where(PeriodicReview.profile_id == profile.id))
    session.execute(delete(Mention).where(Mention.profile_id == profile.id))
    # Before deliverables: RESTRICT.
    session.execute(delete(SkillLevelChange).where(SkillLevelChange.profile_id == profile.id))
    session.execute(delete(SkillState).where(SkillState.profile_id == profile.id))

    deliverable_ids = list(
        session.scalars(select(Deliverable.id).where(Deliverable.profile_id == profile.id))
    )
    if deliverable_ids:
        session.execute(
            delete(DeliverableSkill).where(DeliverableSkill.deliverable_id.in_(deliverable_ids))
        )
        session.execute(
            delete(DeliverableImpact).where(
                DeliverableImpact.deliverable_id.in_(deliverable_ids)
            )
        )
        session.execute(delete(Deliverable).where(Deliverable.id.in_(deliverable_ids)))

    session.flush()


def _insert_cause_tree(
    session: Session,
    *,
    nodes: list[dict[str, Any]],
    parent: CauseNode | None,
    case_id: int,
    assumption_by_code: dict[str, Assumption],
) -> int:
    """Walk the nested YAML cause tree depth-first, returning the node count.

    Kept at module level and given its dependencies explicitly rather than
    closing over the enclosing loop's variables: a closure defined inside a
    `for` loop captures the variable, not its value at definition time, which
    is a real bug waiting for the day this file seeds more than one case.
    """
    created = 0
    for ordinal, node_row in enumerate(nodes):
        node = CauseNode(
            case_id=case_id,
            parent_id=parent.id if parent else None,
            label=node_row["label"],
            description=(node_row.get("description") or "").strip() or None,
            ordinal=ordinal,
            evidence_note=(node_row.get("evidence_note") or "").strip() or None,
        )
        session.add(node)
        session.flush()
        created += 1
        for index, driver_code in enumerate(node_row.get("drivers", [])):
            session.add(
                CauseDriver(
                    cause_node_id=node.id,
                    assumption_id=assumption_by_code[driver_code].id,
                    ordinal=index,
                )
            )
        created += _insert_cause_tree(
            session,
            nodes=node_row.get("children", []),
            parent=node,
            case_id=case_id,
            assumption_by_code=assumption_by_code,
        )
    return created


def seed_demo(session: Session, seeds_dir: Path | None = None) -> dict[str, int]:
    seeds_dir = seeds_dir or get_settings().seeds_dir
    data = _load_yaml(seeds_dir / "demo" / "demo_profile.yaml")
    counts: dict[str, int] = {}

    profile_row = data["profile"]
    profile = session.scalar(select(Profile).where(Profile.code == profile_row["code"]))
    if profile is None:
        profile = Profile(code=profile_row["code"])
        session.add(profile)
    profile.display_name = profile_row["display_name"]
    profile.is_demo = True
    profile.based_in = profile_row.get("based_in")
    profile.currency = profile_row.get("currency", "EUR")
    session.flush()

    reset_profile_data(session, profile)

    skills = {s.code: s for s in session.scalars(select(Skill))}
    types = {t.code: t for t in session.scalars(select(DeliverableType))}
    criteria = {c.code: c for c in session.scalars(select(ReviewCriterion))}
    roles = {r.code: r for r in session.scalars(select(TargetRole))}

    # --- Deliverables -------------------------------------------------------
    deliverable_by_ref: dict[str, Deliverable] = {}
    for row in data.get("deliverables", []):
        deliverable = Deliverable(
            profile_id=profile.id,
            type_id=types[row["type"]].id,
            title=row["title"],
            summary=(row.get("summary") or "").strip() or None,
            status=row["status"],
            started_on=row.get("started_on"),
            published_on=row.get("published_on"),
            artifact_url=row.get("artifact_url"),
            business_value=_dec(row.get("business_value")),
        )
        session.add(deliverable)
        session.flush()
        deliverable_by_ref[row["ref"]] = deliverable

        for link in row.get("skills", []):
            session.add(
                DeliverableSkill(
                    deliverable_id=deliverable.id,
                    skill_id=skills[link["skill"]].id,
                    contribution=link.get("contribution", 2),
                )
            )
        for impact in row.get("impacts", []):
            session.add(
                DeliverableImpact(
                    deliverable_id=deliverable.id,
                    metric_code=impact["metric"],
                    value=_dec(impact["value"]),
                    unit=impact.get("unit"),
                    measured_on=impact["measured_on"],
                    source=impact.get("source"),
                )
            )
    counts["deliverables"] = len(deliverable_by_ref)

    # --- Skill states and their evidence trail ------------------------------
    for row in data.get("skill_states", []):
        session.add(
            SkillState(
                profile_id=profile.id,
                skill_id=skills[row["skill"]].id,
                current_level=row["current_level"],
                target_level=row["target_level"],
                last_practised_on=row.get("last_practised_on"),
                notes=(row.get("notes") or "").strip() or None,
            )
        )
    counts["skill_states"] = len(data.get("skill_states", []))

    for row in data.get("level_changes", []):
        evidence = deliverable_by_ref.get(row["evidence"]) if row.get("evidence") else None
        session.add(
            SkillLevelChange(
                profile_id=profile.id,
                skill_id=skills[row["skill"]].id,
                from_level=row["from_level"],
                to_level=row["to_level"],
                changed_on=row["changed_on"],
                deliverable_id=evidence.id if evidence else None,
                rationale=(row.get("rationale") or "").strip() or None,
            )
        )
    counts["level_changes"] = len(data.get("level_changes", []))

    for row in data.get("mentions", []):
        session.add(
            Mention(
                profile_id=profile.id,
                deliverable_id=(
                    deliverable_by_ref[row["deliverable"]].id if row.get("deliverable") else None
                ),
                occurred_on=row["occurred_on"],
                source=row["source"],
                url=row.get("url"),
                note=(row.get("note") or "").strip() or None,
            )
        )
    counts["mentions"] = len(data.get("mentions", []))

    # --- Market postings ----------------------------------------------------
    for row in data.get("job_postings", []):
        posting = JobPosting(
            target_role_id=roles[row["target_role"]].id if row.get("target_role") else None,
            title=row["title"],
            company=row.get("company"),
            location=row.get("location"),
            seniority_label=row.get("seniority_label"),
            source=row.get("source"),
            posted_on=row.get("posted_on"),
            captured_on=row["captured_on"],
            raw_text=row["raw_text"].strip(),
        )
        session.add(posting)
        session.flush()
        for req in row.get("requirements", []):
            session.add(
                JobRequirement(
                    posting_id=posting.id,
                    raw_label=req["raw_label"],
                    skill_id=skills[req["skill"]].id if req.get("skill") else None,
                    required_level=req.get("required_level"),
                    importance=req.get("importance", "must_have"),
                    evidence_quote=req.get("evidence_quote"),
                )
            )
    counts["job_postings"] = len(data.get("job_postings", []))

    # --- Business cases -----------------------------------------------------
    cases = _load_yaml(seeds_dir / "demo" / "demo_business_case.yaml")
    counts["business_cases"] = 0
    for case_row in cases.get("business_cases", []):
        case = BusinessCase(
            profile_id=profile.id,
            title=case_row["title"],
            company_context=(case_row.get("company_context") or "").strip() or None,
            industry=case_row.get("industry"),
            symptom=case_row["symptom"].strip(),
            claimed_annual_loss=_dec(case_row.get("claimed_annual_loss")),
            currency=case_row.get("currency", "EUR"),
            status=case_row.get("status", "draft"),
            opened_on=case_row["opened_on"],
        )
        session.add(case)
        session.flush()
        counts["business_cases"] += 1

        assumption_by_code: dict[str, Assumption] = {}
        for row in case_row.get("assumptions", []):
            assumption = Assumption(
                case_id=case.id,
                code=row["code"],
                label=row["label"],
                unit=row.get("unit"),
                base_value=_dec(row["base_value"]),
                low_value=_dec(row.get("low_value")),
                high_value=_dec(row.get("high_value")),
                source=(row.get("source") or "").strip() or None,
                confidence=row.get("confidence", "medium"),
                rationale=(row.get("rationale") or "").strip() or None,
            )
            session.add(assumption)
            assumption_by_code[row["code"]] = assumption
        session.flush()

        counts["cause_nodes"] = counts.get("cause_nodes", 0) + _insert_cause_tree(
            session,
            nodes=case_row.get("cause_tree", []),
            parent=None,
            case_id=case.id,
            assumption_by_code=assumption_by_code,
        )

        solution_row = case_row.get("solution")
        if solution_row:
            solution = Solution(
                case_id=case.id,
                **{
                    field: (solution_row.get(field) or "").strip() or None
                    for field in (
                        "data_requirements",
                        "architecture",
                        "ai_component",
                        "automation_component",
                        "process_change",
                        "governance",
                        "deployment_plan",
                        "key_risks",
                    )
                },
            )
            session.add(solution)
            session.flush()
            for kpi in solution_row.get("kpis", []):
                session.add(
                    SolutionKpi(
                        solution_id=solution.id,
                        name=kpi["name"],
                        definition=(kpi.get("definition") or "").strip() or None,
                        unit=kpi.get("unit"),
                        baseline_value=_dec(kpi.get("baseline_value")),
                        target_value=_dec(kpi.get("target_value")),
                        measurement_frequency=kpi.get("measurement_frequency"),
                        data_source=kpi.get("data_source"),
                    )
                )

        model_by_version: dict[int, RoiModel] = {}
        for model_row in case_row.get("roi_models", []):
            roi_model = RoiModel(
                case_id=case.id,
                version=model_row["version"],
                horizon_years=model_row["horizon_years"],
                discount_rate=_dec(model_row["discount_rate"]),
                currency=model_row.get("currency", case.currency),
                notes=(model_row.get("notes") or "").strip() or None,
            )
            session.add(roi_model)
            session.flush()
            model_by_version[model_row["version"]] = roi_model
            for line in model_row.get("lines", []):
                session.add(
                    RoiLine(
                        roi_model_id=roi_model.id,
                        kind=line["kind"],
                        category=line["category"],
                        label=line["label"],
                        year_index=line["year_index"],
                        amount_assumption_id=assumption_by_code[line["amount"]].id,
                        quantity=_dec(line.get("quantity", 1)),
                        notes=(line.get("notes") or "").strip() or None,
                    )
                )

        for review_row in case_row.get("reviews", []):
            review = CaseReview(
                case_id=case.id,
                roi_model_id=(
                    model_by_version[review_row["roi_model_version"]].id
                    if review_row.get("roi_model_version")
                    else None
                ),
                reviewed_on=review_row["reviewed_on"],
                overall_score=_dec(review_row["overall_score"]),
                verdict=(review_row.get("verdict") or "").strip() or None,
                summary=(review_row.get("summary") or "").strip() or None,
            )
            session.add(review)
            session.flush()
            for score in review_row.get("scores", []):
                session.add(
                    CaseReviewScore(
                        review_id=review.id,
                        criterion_id=criteria[score["criterion"]].id,
                        score=_dec(score["score"]),
                        comment=(score.get("comment") or "").strip() or None,
                    )
                )
            for challenge in review_row.get("challenges", []):
                target = challenge.get("target_assumption")
                session.add(
                    CaseReviewChallenge(
                        review_id=review.id,
                        persona=challenge["persona"],
                        severity=challenge["severity"],
                        target_assumption_id=(
                            assumption_by_code[target].id if target else None
                        ),
                        target_area=challenge.get("target_area"),
                        challenge=challenge["challenge"].strip(),
                        evidence_demanded=(
                            challenge.get("evidence_demanded") or ""
                        ).strip()
                        or None,
                        response=(challenge.get("response") or "").strip() or None,
                        resolved_on=challenge.get("resolved_on"),
                    )
                )

    for row in data.get("periodic_reviews", []):
        session.add(
            PeriodicReview(
                profile_id=profile.id,
                kind=row["kind"],
                period_start=row["period_start"],
                period_end=row["period_end"],
                body_md=row["body_md"].strip(),
                next_action=(row.get("next_action") or "").strip() or None,
                next_action_rationale=(row.get("next_action_rationale") or "").strip() or None,
            )
        )
    counts["periodic_reviews"] = len(data.get("periodic_reviews", []))

    return counts


def ensure_owner_profile(session: Session, code: str, display_name: str) -> Profile:
    """Create the real (non-demo) profile if it does not exist yet."""
    profile = session.scalar(select(Profile).where(Profile.code == code))
    if profile is None:
        profile = Profile(code=code, display_name=display_name, is_demo=False)
        session.add(profile)
        session.flush()
    return profile


__all__ = [
    "ensure_owner_profile",
    "reset_profile_data",
    "seed_demo",
    "seed_reference",
]
