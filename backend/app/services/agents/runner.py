"""Prompt loading and the agent execution log.

Every model call is a row in `agent_run`, and everything an agent produces
points back at the run that produced it. The reason is reproducibility: a
critique that scored a case 6.28 in 2027 is only interpretable if you know
which prompt version and which model produced it.

`prompt_sha256` is the hash of the file actually read at call time. A prompt
edited afterwards will not match the hash stored against the run, so it cannot
silently pass for the one that produced the result. That is the difference
between a version note and a verifiable claim.

The failure path matters as much as the success path. A run that raises is
still committed, with `status='failed'` and the error text, before the
exception is re-raised. An agent that fails silently is worse than one that
fails loudly, and a log with only successes in it is not a log.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, get_settings
from app.models import AgentRun
from app.services.agents.client import AgentError, LlmClient

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "services" / "agents" / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    path: Path
    relative_path: str
    sha256: str
    text: str


def load_prompt(name: str, prompts_dir: Path | None = None) -> Prompt:
    directory = prompts_dir or PROMPTS_DIR
    path = directory / f"{name}.md"
    if not path.exists():
        available = sorted(p.stem for p in directory.glob("*.md") if p.stem != "README")
        raise AgentError(f"no prompt named '{name}'. Available: {', '.join(available)}")

    raw = path.read_bytes()
    return Prompt(
        name=name,
        path=path,
        relative_path=str(path.relative_to(REPO_ROOT)),
        sha256=hashlib.sha256(raw).hexdigest(),
        text=raw.decode("utf-8"),
    )


def verify_prompt(run: AgentRun, prompts_dir: Path | None = None) -> bool:
    """Is the prompt file on disk still the one that produced this run?

    False does not mean the run was wrong — it means the prompt has changed
    since, and the result should not be compared with newer ones as though
    they came from the same instructions.
    """
    try:
        current = load_prompt(Path(run.prompt_path).stem, prompts_dir)
    except AgentError:
        return False
    return current.sha256 == run.prompt_sha256


def run_agent(
    session: Session,
    *,
    agent_name: str,
    prompt_name: str,
    payload: dict[str, Any],
    output_model: type[T],
    client: LlmClient,
    model: str | None = None,
    max_tokens: int = 8000,
    prompts_dir: Path | None = None,
) -> tuple[AgentRun, T]:
    """Execute one agent call and log it, whatever happens.

    The caller supplies the client, so nothing here reaches the network by
    itself and every test runs against a stub.
    """
    prompt = load_prompt(prompt_name, prompts_dir)
    chosen_model = model or get_settings().anthropic_model

    run = AgentRun(
        agent_name=agent_name,
        prompt_path=prompt.relative_path,
        prompt_sha256=prompt.sha256,
        model=chosen_model,
        status="pending",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        response = client.complete(
            system=prompt.text,
            user=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            json_schema=_tool_schema(output_model),
            model=chosen_model,
            max_tokens=max_tokens,
        )
        parsed = output_model.model_validate(response.data)
    except ValidationError as exc:
        _fail(session, run, f"the model's output did not match the schema: {exc}")
        raise AgentError(f"invalid agent output: {exc}") from exc
    except Exception as exc:
        _fail(session, run, str(exc))
        raise

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.input_tokens = response.input_tokens
    run.output_tokens = response.output_tokens
    session.flush()
    return run, parsed


def _fail(session: Session, run: AgentRun, message: str) -> None:
    run.status = "failed"
    run.finished_at = datetime.now(UTC)
    run.error = message[:4000]
    session.flush()


def _tool_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic's JSON schema, flattened for the tool-use API.

    `$defs` and `$ref` are inlined because the tool input schema is validated
    by the API without following references, and a nested model would
    otherwise arrive as an unresolvable pointer.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return _inline_refs(schema, definitions)


def _inline_refs(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            resolved = definitions.get(name, {})
            merged = {**_inline_refs(resolved, definitions)}
            for key, value in node.items():
                if key != "$ref":
                    merged[key] = _inline_refs(value, definitions)
            return merged
        return {key: _inline_refs(value, definitions) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline_refs(item, definitions) for item in node]
    return node
