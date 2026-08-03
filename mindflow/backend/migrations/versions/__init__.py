"""Migration scripts.

`_load_tenant_tables` lets the isolation test compare the policy lists declared
across the migrations against the model list, so a table added without a policy
fails the build instead of leaking silently.

Phase 2 adds tables in migration 0005, which declares its own policies there
rather than amending 0002 — a released migration is not edited. The helper
therefore unions the declarations, and the test's guarantee is unchanged: every
table in `TENANT_TABLES` is covered by a policy somewhere.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# (file, attribute) pairs declaring RLS-covered tables. Adding a migration that
# creates tenant tables means adding it here — and the isolation test fails
# until you do.
POLICY_SOURCES: tuple[tuple[str, str], ...] = (
    ("0002_row_level_security.py", "TENANT_TABLES"),
    ("0005_planning_reminders_notifications_history.py", "NEW_TENANT_TABLES"),
    ("0006_ai_layer_vectors_entities_conversations.py", "NEW_TENANT_TABLES"),
)


def _load_module(filename: str) -> object:
    path = Path(__file__).parent / filename
    spec = importlib.util.spec_from_file_location(f"_migration_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_tenant_tables() -> tuple[str, ...]:
    tables: list[str] = []
    for filename, attribute in POLICY_SOURCES:
        module = _load_module(filename)
        tables.extend(getattr(module, attribute))
    return tuple(tables)
