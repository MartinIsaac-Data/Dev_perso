"""Command line entry point.

Everything that is not an HTTP request lives here: migrations, seeding, graph
checks and (from Phase 4) the analytical build and Parquet export. Keeping
them in a CLI rather than in ad-hoc scripts means they are importable,
testable and runnable identically on a laptop and inside the container.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from sqlalchemy import func, select

from app.config import REPO_ROOT, get_settings
from app.db import session_scope
from app.models import AgentRun, BusinessCase, Profile, Skill, SkillEdge
from app.services.graph import descendants, find_cycle, topological_order
from app.services.seeding import ensure_owner_profile, seed_demo, seed_reference

app = typer.Typer(help="Transformation OS — operational commands", no_args_is_help=True)
db_app = typer.Typer(help="Database migrations")
seed_app = typer.Typer(help="Seed loading")
graph_app = typer.Typer(help="Skill graph inspection")
agent_app = typer.Typer(help="Agents: review board, extraction, periodic review")
app.add_typer(db_app, name="db")
app.add_typer(seed_app, name="seed")
app.add_typer(graph_app, name="graph")
app.add_typer(agent_app, name="agent")


def _alembic(*args: str) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Apply migrations up to REVISION (default: head)."""
    _alembic("upgrade", revision)


@db_app.command("downgrade")
def db_downgrade(revision: str) -> None:
    """Roll back to REVISION."""
    _alembic("downgrade", revision)


@db_app.command("current")
def db_current() -> None:
    """Show the revision the database is currently at."""
    _alembic("current", "--verbose")


@db_app.command("revision")
def db_revision(message: str, autogenerate: bool = True) -> None:
    """Create a new migration by diffing the models against the database."""
    args = ["revision", "-m", message]
    if autogenerate:
        args.append("--autogenerate")
    _alembic(*args)


@seed_app.command("reference")
def seed_reference_cmd() -> None:
    """Load or update the taxonomy, phases, types and rubric.

    Idempotent and safe against a database holding real data.
    """
    with session_scope() as session:
        counts = seed_reference(session)
    for key, value in counts.items():
        typer.echo(f"  {key:<20} {value}")
    typer.secho("reference seed applied", fg=typer.colors.GREEN)


@seed_app.command("demo")
def seed_demo_cmd() -> None:
    """Rebuild the demonstration profile. Destructive for that profile only."""
    with session_scope() as session:
        counts = seed_demo(session)
    for key, value in counts.items():
        typer.echo(f"  {key:<20} {value}")
    typer.secho("demo profile rebuilt", fg=typer.colors.GREEN)


@seed_app.command("all")
def seed_all_cmd(
    owner_code: str = typer.Option("owner", help="Code for your real profile."),
    owner_name: str = typer.Option("Owner", help="Display name for your real profile."),
) -> None:
    """Reference seed, demo profile, and an empty real profile."""
    with session_scope() as session:
        seed_reference(session)
        seed_demo(session)
        ensure_owner_profile(session, owner_code, owner_name)
    typer.secho("reference + demo + owner profile ready", fg=typer.colors.GREEN)


@graph_app.command("check")
def graph_check() -> None:
    """Verify the stored skill graph is acyclic and report its shape."""
    with session_scope() as session:
        edges = [
            (e.prerequisite_skill_id, e.dependent_skill_id)
            for e in session.scalars(select(SkillEdge))
        ]
        names = {s.id: s.code for s in session.scalars(select(Skill))}

    cycle = find_cycle(edges)
    if cycle is not None:
        rendered = " -> ".join(names.get(n, str(n)) for n in cycle)
        typer.secho(f"CYCLE DETECTED: {rendered}", fg=typer.colors.RED)
        raise typer.Exit(1)

    order = topological_order(edges, nodes=names)
    roots = sorted(names[n] for n in names if not any(b == n for _, b in edges))
    leaves = sorted(names[n] for n in names if not any(a == n for a, _ in edges))
    typer.echo(f"  skills            {len(names)}")
    typer.echo(f"  edges             {len(edges)}")
    typer.echo(f"  roots             {len(roots)}")
    typer.echo(f"  leaves            {len(leaves)}")
    typer.echo(f"  longest chain     {_longest_chain(edges, order)}")
    typer.secho("graph is acyclic", fg=typer.colors.GREEN)


def _longest_chain(edges: list[tuple[int, int]], order: list[int]) -> int:
    """Depth of the deepest prerequisite chain, in nodes."""
    depth: dict[int, int] = dict.fromkeys(order, 1)
    successors: dict[int, list[int]] = {}
    for a, b in edges:
        successors.setdefault(a, []).append(b)
    for node in order:
        for nxt in successors.get(node, []):
            depth[nxt] = max(depth.get(nxt, 1), depth[node] + 1)
    return max(depth.values()) if depth else 0


@graph_app.command("critical")
def graph_critical(limit: int = 12) -> None:
    """List the skills that gate the most other skills downstream."""
    with session_scope() as session:
        edges = [
            (e.prerequisite_skill_id, e.dependent_skill_id)
            for e in session.scalars(select(SkillEdge))
        ]
        skills = {s.id: s for s in session.scalars(select(Skill))}

    ranked = sorted(
        ((len(descendants(edges, sid)), skills[sid].code) for sid in skills),
        reverse=True,
    )
    for count, code in ranked[:limit]:
        typer.echo(f"  {count:>3}  {code}")


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------


def _resolve_profile(session, code: str):  # noqa: ANN001
    profile = session.scalar(select(Profile).where(Profile.code == code))
    if profile is None:
        known = ", ".join(p.code for p in session.scalars(select(Profile)))
        typer.secho(f"unknown profile '{code}'. Known: {known}", fg=typer.colors.RED)
        raise typer.Exit(1)
    return profile


@agent_app.command("review-case")
def agent_review_case(
    case_id: int,
    version: int | None = typer.Option(None, help="ROI model version. Defaults to latest."),
    profile: str = typer.Option("demo", help="Profile owning the case."),
) -> None:
    """Run the adversarial review board against a business case."""
    from app.services.agents.client import AgentError, default_client
    from app.services.agents.review_board import review_case

    try:
        client = default_client()
    except AgentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(2) from exc

    with session_scope() as session:
        owner = _resolve_profile(session, profile)
        case = session.get(BusinessCase, case_id)
        if case is None or case.profile_id != owner.id:
            typer.secho(f"no business case {case_id} on profile '{profile}'", fg=typer.colors.RED)
            raise typer.Exit(1)

        model = None
        if version is not None:
            model = next((m for m in case.roi_models if m.version == version), None)
            if model is None:
                typer.secho(f"no ROI model version {version}", fg=typer.colors.RED)
                raise typer.Exit(1)

        try:
            review = review_case(session, case, client, roi_model=model)
        except AgentError as exc:
            typer.secho(f"the review failed: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        typer.echo(f"  score        {review.overall_score}/10")
        typer.echo(f"  challenges   {len(review.challenges)}")
        blocking = sum(1 for c in review.challenges if c.severity == "blocking")
        typer.echo(f"  blocking     {blocking}")
        typer.echo("")
        typer.echo(f"  {review.verdict}")
    typer.secho("review recorded", fg=typer.colors.GREEN)


@agent_app.command("extract")
def agent_extract(
    path: str = typer.Argument(..., help="File containing the raw advert text."),
    role: str | None = typer.Option(None, help="Target role code to attach it to."),
    source: str | None = typer.Option(None, help="Where the advert came from."),
) -> None:
    """Turn a job advert into structured requirements."""
    from app.services.agents.client import AgentError, default_client
    from app.services.agents.extraction import extract_posting

    text = Path(path).read_text(encoding="utf-8")
    try:
        client = default_client()
    except AgentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(2) from exc

    with session_scope() as session:
        try:
            posting = extract_posting(
                session, text, client, target_role_code=role, source=source
            )
        except AgentError as exc:
            typer.secho(f"extraction failed: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        mapped = sum(1 for r in posting.requirements if r.skill_id is not None)
        typer.echo(f"  title        {posting.title}")
        typer.echo(f"  requirements {len(posting.requirements)}")
        typer.echo(f"  mapped       {mapped}")
        typer.echo(f"  unmapped     {len(posting.requirements) - mapped}")
        for requirement in posting.requirements:
            if requirement.skill_id is None:
                typer.echo(f"    ? {requirement.raw_label}")
    typer.secho("posting recorded", fg=typer.colors.GREEN)


@agent_app.command("review")
def agent_periodic_review(
    kind: str = typer.Argument("weekly", help="weekly or quarterly"),
    profile: str = typer.Option("demo"),
) -> None:
    """Generate the weekly or quarterly review."""
    from app.services.agents.client import AgentError, default_client
    from app.services.agents.periodic_review import generate_review

    try:
        client = default_client()
    except AgentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(2) from exc

    with session_scope() as session:
        owner = _resolve_profile(session, profile)
        try:
            review = generate_review(session, owner, kind, client)
        except (AgentError, ValueError) as exc:
            typer.secho(f"the review failed: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        typer.echo("")
        typer.echo(review.body_md)
        typer.echo("")
        typer.secho(f"  NEXT: {review.next_action}", fg=typer.colors.CYAN)
        typer.echo(f"  because {review.next_action_rationale}")


@agent_app.command("runs")
def agent_runs(limit: int = 15) -> None:
    """Recent agent calls, with whether their prompt has changed since."""
    from app.services.agents.runner import verify_prompt

    with session_scope() as session:
        runs = list(
            session.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))
        )
        if not runs:
            typer.echo("  no agent runs recorded")
            return
        for run in runs:
            fresh = "prompt unchanged" if verify_prompt(run) else "PROMPT HAS CHANGED"
            tokens = f"{run.input_tokens or 0}/{run.output_tokens or 0}"
            typer.echo(
                f"  {run.started_at:%Y-%m-%d %H:%M}  {run.agent_name:<24} "
                f"{run.status:<10} {tokens:>12}  {fresh}"
            )
            if run.error:
                typer.echo(f"      {run.error[:120]}")


@app.command("status")
def status() -> None:
    """One-line summary of what is in the database."""
    settings = get_settings()
    typer.echo(f"database  {settings.database_url}")
    with session_scope() as session:
        skills = session.scalar(select(func.count()).select_from(Skill))
        edges = session.scalar(select(func.count()).select_from(SkillEdge))
        profiles = list(session.scalars(select(Profile)))
    typer.echo(f"skills    {skills}")
    typer.echo(f"edges     {edges}")
    for profile in profiles:
        suffix = " (demo)" if profile.is_demo else ""
        typer.echo(f"profile   {profile.code}{suffix} — {profile.display_name}")


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["app", "main"]
