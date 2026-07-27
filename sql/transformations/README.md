# Analytical transformations

Versioned SQL that builds the star schema from the normalised tables. Executed
by `python -m app.cli analytics build` (Phase 4), never by Alembic — see
ADR-010.

## Conventions

- Files are numbered and run in order: `010_dim_date.sql`, `020_dim_skill.sql`,
  `100_fact_activity.sql`. Gaps in the numbering are intentional, so a
  transformation can be inserted without renumbering everything after it.
- Every file is idempotent: `DROP TABLE IF EXISTS` then `CREATE TABLE AS`. The
  star layer is rebuilt, never migrated.
- Every file starts with a comment block stating the **grain** of the table it
  produces — one row per what. A fact table whose grain is not stated in one
  sentence is a fact table that will be double-counted.
- Only `fact_*` and `dim_*` names. `alembic/env.py` uses that prefix to know
  what to leave alone.
- Plain SQL that both SQLite and PostgreSQL accept. No dialect-specific
  functions; where one is unavoidable, it is isolated in its own file with the
  reason stated.

The SQL here is written to be read. It is the part of this repository closest
to what the target roles actually require, so it is commented for someone
learning the pattern, not for someone who already knows it.

## Planned tables

| Table | Grain |
| --- | --- |
| `dim_date` | One row per calendar day, with quarter and phase attributes |
| `dim_skill` | One row per skill, with its domain and graph position |
| `dim_deliverable_type` | One row per deliverable type |
| `dim_profile` | One row per profile |
| `fact_activity` | One row per deliverable-skill pair, at publication date |
| `fact_skill_state` | One row per profile-skill-snapshot |
| `fact_case_review` | One row per case review criterion score |
| `fact_market_requirement` | One row per requirement extracted from a posting |
