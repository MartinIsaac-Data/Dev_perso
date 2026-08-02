"""Migration scripts.

`_load_tenant_tables` lets the isolation test compare the policy list declared in
migration 0002 against the model list, so a table added without a policy fails the
build instead of leaking silently.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_tenant_tables() -> tuple[str, ...]:
    path = Path(__file__).parent / "0002_row_level_security.py"
    spec = importlib.util.spec_from_file_location("_rls_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.TENANT_TABLES)
