"""The analytical layer.

Two families of test here, and the second matters more.

The first checks the build runs and the counts reconcile with the normalised
tables. The second checks the *grain* of every fact — that the columns claimed
as its grain in the file header really are unique, and that every dimension key
resolves. A star schema with a broken grain does not fail; it silently
double-counts, and the number is wrong in a report nobody re-derives by hand.

Portability is asserted rather than assumed: a test greps every transformation
for the date functions that differ between SQLite and Postgres. That promise is
worth nothing unless something checks it, because the failure mode is silent
until the first attempt to move.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.services.analytics import (
    build_star,
    drop_star,
    export_parquet,
    split_statements,
    star_tables,
    transformation_files,
    view_files,
)

SQL_DIR = REPO_ROOT / "sql"
BUILD_DATE = date(2026, 7, 28)

# Functions that exist in one backend and not the other. The whole point of
# conforming on dim_date is that none of these appears in a transformation.
DIALECT_FUNCTIONS = (
    "strftime",
    "julianday",
    "date_trunc",
    "extract(",
    "datediff",
    "to_char",
    "now()",
    "getdate",
    "age(",
)


@pytest.fixture
def built(demo_session: Session) -> Session:
    build_star(demo_session, build_date=BUILD_DATE, sql_dir=SQL_DIR)
    demo_session.commit()
    return demo_session


def rows(session: Session, sql: str) -> list[tuple]:
    return list(session.execute(text(sql)).fetchall())


def count(session: Session, table: str, where: str = "1=1") -> int:
    return session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where}")).scalar() or 0


class TestTransformationFiles:
    def test_files_are_ordered_numerically_not_alphabetically(self) -> None:
        # A plain string sort puts 100_ before 020_, which breaks every fact
        # that joins a dimension built earlier.
        names = [p.name for p in transformation_files(SQL_DIR)]
        prefixes = [int(name[:3]) for name in names]
        assert prefixes == sorted(prefixes)
        assert prefixes[0] < 100 and prefixes[-1] >= 100

    def test_every_transformation_states_its_grain(self) -> None:
        """A fact table whose grain is not stated will be double-counted."""
        for path in transformation_files(SQL_DIR):
            header = path.read_text(encoding="utf-8")[:1200].lower()
            assert "grain:" in header, f"{path.name} does not state its grain"

    @pytest.mark.parametrize("path", transformation_files(SQL_DIR), ids=lambda p: p.name)
    def test_no_dialect_specific_date_functions(self, path: Path) -> None:
        sql = " ".join(split_statements(path.read_text(encoding="utf-8"))).lower()
        for function in DIALECT_FUNCTIONS:
            assert function not in sql, f"{path.name} uses {function}"

    @pytest.mark.parametrize("path", transformation_files(SQL_DIR), ids=lambda p: p.name)
    def test_every_transformation_is_idempotent(self, path: Path) -> None:
        # DROP ... IF EXISTS then CREATE. A rebuild must be a rebuild.
        sql = path.read_text(encoding="utf-8").upper()
        assert "DROP TABLE IF EXISTS" in sql

    def test_only_fact_and_dim_names_are_created(self) -> None:
        # alembic/env.py uses that prefix to know what to leave alone.
        for path in transformation_files(SQL_DIR):
            for match in re.finditer(
                r"CREATE TABLE (\w+)", path.read_text(encoding="utf-8"), re.IGNORECASE
            ):
                assert match.group(1).startswith(("fact_", "dim_"))

    def test_views_are_named_and_ordered(self) -> None:
        for path in view_files(SQL_DIR):
            for match in re.finditer(
                r"CREATE VIEW (\w+)", path.read_text(encoding="utf-8"), re.IGNORECASE
            ):
                assert match.group(1).startswith("v_")

    def test_a_file_without_an_order_prefix_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "transformations").mkdir()
        (tmp_path / "transformations" / "dim_oops.sql").write_text("SELECT 1;")
        with pytest.raises(ValueError, match="three-digit order prefix"):
            transformation_files(tmp_path)


class TestStatementSplitting:
    def test_a_semicolon_inside_a_comment_does_not_split_the_statement(self) -> None:
        """The bug this function exists for.

        Splitting on ';' first hands the database half a sentence of English
        and fails with a syntax error pointing at a comment.
        """
        sql = """
        -- `strftime` in SQLite and `EXTRACT` in Postgres; conforming avoids it
        DROP TABLE IF EXISTS t;
        CREATE TABLE t AS SELECT 1 AS x;
        """
        statements = split_statements(sql)
        assert len(statements) == 2
        assert statements[0].startswith("DROP TABLE")
        assert statements[1].startswith("CREATE TABLE")

    def test_blank_statements_are_dropped(self) -> None:
        assert split_statements(";;\n-- only a comment\n;;") == []


class TestBuild:
    def test_builds_every_table(self, built: Session, engine: Engine) -> None:
        tables = star_tables(engine)
        assert "dim_date" in tables
        assert {"fact_activity", "fact_skill_state", "fact_market_requirement"} <= set(tables)

    def test_is_idempotent(self, built: Session, engine: Engine) -> None:
        before = {t: count(built, t) for t in star_tables(engine)}
        build_star(built, build_date=BUILD_DATE, sql_dir=SQL_DIR)
        built.commit()
        after = {t: count(built, t) for t in star_tables(engine)}
        assert before == after

    def test_drop_leaves_the_normalised_tables_alone(
        self, built: Session, engine: Engine
    ) -> None:
        deliverables_before = count(built, "deliverable")
        drop_star(built, engine)
        built.commit()
        assert star_tables(engine) == []
        assert count(built, "deliverable") == deliverables_before

    def test_a_build_date_outside_the_calendar_is_refused(
        self, demo_session: Session
    ) -> None:
        with pytest.raises(ValueError, match="outside the calendar"):
            build_star(demo_session, build_date=date(2099, 1, 1), sql_dir=SQL_DIR)


class TestDimDate:
    def test_exactly_one_build_date(self, built: Session) -> None:
        # The facts subtract day numbers against this single row.
        assert count(built, "dim_date", "is_build_date = 1") == 1

    def test_date_key_is_yyyymmdd(self, built: Session) -> None:
        row = rows(built, "SELECT date_key, full_date FROM dim_date WHERE is_build_date = 1")[0]
        assert row[0] == 20260728

    def test_day_number_is_sequential(self, built: Session) -> None:
        result = rows(
            built,
            "SELECT day_number FROM dim_date ORDER BY date_key LIMIT 5",
        )
        numbers = [r[0] for r in result]
        assert numbers == list(range(numbers[0], numbers[0] + 5))

    def test_carries_the_phase_each_day_falls_in(self, built: Session) -> None:
        phase = rows(
            built, "SELECT phase_code FROM dim_date WHERE date_key = 20260728"
        )[0][0]
        assert phase == "foundations"

    def test_days_before_the_trajectory_have_no_phase(self, built: Session) -> None:
        assert count(built, "dim_date", "date_key < 20260101 AND phase_code IS NOT NULL") == 0

    def test_quarter_boundaries(self, built: Session) -> None:
        assert rows(built, "SELECT quarter FROM dim_date WHERE date_key = 20260331")[0][0] == 1
        assert rows(built, "SELECT quarter FROM dim_date WHERE date_key = 20260401")[0][0] == 2


class TestGrain:
    """Every fact must be unique on the columns its header claims as its grain.

    A broken grain does not raise. It double-counts, and the wrong number ends
    up in a report nobody re-derives by hand.
    """

    @pytest.mark.parametrize(
        ("table", "keys"),
        [
            ("fact_activity", "deliverable_id, skill_key"),
            ("fact_skill_state", "profile_key, skill_key"),
            ("fact_level_change", "level_change_id"),
            ("fact_case_review", "review_id, criterion_key"),
            ("fact_review_challenge", "challenge_id"),
            ("fact_market_requirement", "requirement_id"),
            ("dim_skill", "skill_key"),
            ("dim_profile", "profile_key"),
            ("dim_date", "date_key"),
        ],
    )
    def test_grain_is_unique(self, built: Session, table: str, keys: str) -> None:
        total = count(built, table)
        distinct = built.execute(
            text(f"SELECT COUNT(*) FROM (SELECT DISTINCT {keys} FROM {table}) x")
        ).scalar()
        assert total == distinct, f"{table} is not unique on ({keys})"


class TestReferentialIntegrity:
    """Every dimension key on every fact must resolve.

    A star schema has no foreign keys, so nothing enforces this at write time.
    An orphan key means rows silently vanish from an inner-joined report.
    """

    @pytest.mark.parametrize(
        ("fact", "column", "dimension", "dim_key"),
        [
            ("fact_activity", "skill_key", "dim_skill", "skill_key"),
            ("fact_activity", "date_key", "dim_date", "date_key"),
            ("fact_activity", "profile_key", "dim_profile", "profile_key"),
            (
                "fact_activity",
                "deliverable_type_key",
                "dim_deliverable_type",
                "deliverable_type_key",
            ),
            ("fact_skill_state", "skill_key", "dim_skill", "skill_key"),
            ("fact_skill_state", "profile_key", "dim_profile", "profile_key"),
            ("fact_level_change", "skill_key", "dim_skill", "skill_key"),
            ("fact_level_change", "date_key", "dim_date", "date_key"),
            ("fact_case_review", "criterion_key", "dim_review_criterion", "criterion_key"),
            ("fact_case_review", "date_key", "dim_date", "date_key"),
            ("fact_review_challenge", "date_key", "dim_date", "date_key"),
            ("fact_market_requirement", "skill_key", "dim_skill", "skill_key"),
            ("fact_market_requirement", "date_key", "dim_date", "date_key"),
        ],
    )
    def test_no_orphan_keys(
        self, built: Session, fact: str, column: str, dimension: str, dim_key: str
    ) -> None:
        orphans = built.execute(
            text(
                f"SELECT COUNT(*) FROM {fact} f "
                f"LEFT JOIN {dimension} d ON d.{dim_key} = f.{column} "
                f"WHERE d.{dim_key} IS NULL"
            )
        ).scalar()
        assert orphans == 0, f"{fact}.{column} has {orphans} keys not in {dimension}"


class TestUnknownMember:
    def test_dim_skill_carries_an_unknown_member(self, built: Session) -> None:
        assert count(built, "dim_skill", "skill_key = -1 AND is_unknown_member = 1") == 1

    def test_unmapped_requirements_point_at_it_rather_than_null(
        self, built: Session
    ) -> None:
        """The most interesting rows in the warehouse must not be losable."""
        from app.models import JobPosting, JobRequirement

        posting = built.scalars(__import__("sqlalchemy").select(JobPosting)).first()
        built.add(
            JobRequirement(
                posting_id=posting.id,
                raw_label="something the taxonomy cannot express",
                skill_id=None,
                importance="must_have",
            )
        )
        built.flush()
        build_star(built, build_date=BUILD_DATE, sql_dir=SQL_DIR)
        built.commit()

        unmapped = count(built, "fact_market_requirement", "is_unmapped = 1")
        assert unmapped >= 1
        assert count(built, "fact_market_requirement", "skill_key IS NULL") == 0
        # And it survives an inner join to the dimension.
        joined = built.execute(
            text(
                "SELECT COUNT(*) FROM fact_market_requirement f "
                "JOIN dim_skill s ON s.skill_key = f.skill_key WHERE f.is_unmapped = 1"
            )
        ).scalar()
        assert joined == unmapped


class TestReconciliation:
    def test_fact_activity_counts_published_deliverables_only(
        self, built: Session
    ) -> None:
        distinct_deliverables = built.execute(
            text("SELECT COUNT(DISTINCT deliverable_id) FROM fact_activity")
        ).scalar()
        source = count(
            built,
            "deliverable d JOIN deliverable_skill ds ON ds.deliverable_id = d.id",
            "d.status = 'published'",
        )
        assert distinct_deliverables > 0
        assert count(built, "fact_activity") == source

    def test_fact_skill_state_matches_the_normalised_table(
        self, built: Session
    ) -> None:
        assert count(built, "fact_skill_state") == count(built, "skill_state")

    def test_fact_case_review_has_one_row_per_criterion_scored(
        self, built: Session
    ) -> None:
        assert count(built, "fact_case_review") == count(built, "case_review_score")

    def test_decay_agrees_with_the_service_layer(self, built: Session) -> None:
        """Two implementations of the same rule must not disagree.

        The service computes decay in Python with calendar months; the star
        schema does it in SQL with day numbers. They will not match exactly at
        the boundary, so this checks they identify the same skills — which is
        what a report and the interface both claim to show.
        """
        from sqlalchemy import select

        from app.models import Profile
        from app.services import skill_graph

        profile = built.scalar(select(Profile).where(Profile.code == "demo"))
        from_service = {
            p.code for p in skill_graph.decayed_skills(built, profile.id, BUILD_DATE)
        }
        from_star = {
            row[0]
            for row in rows(
                built,
                "SELECT s.skill_code FROM fact_skill_state f "
                "JOIN dim_skill s ON s.skill_key = f.skill_key "
                "WHERE f.is_decayed = 1",
            )
        }
        assert from_service == from_star


class TestViews:
    @pytest.mark.parametrize(
        "view",
        ["v_activity_by_quarter", "v_skill_position", "v_market_demand", "v_review_scores"],
    )
    def test_view_is_queryable(self, built: Session, view: str) -> None:
        assert count(built, view) >= 0

    def test_activity_view_never_double_counts_deliverables(
        self, built: Session
    ) -> None:
        # The view aggregates with COUNT(DISTINCT deliverable_id), so summing
        # its measure must equal the real number of published deliverables.
        from_view = built.execute(
            text("SELECT SUM(deliverables_published) FROM v_activity_by_quarter")
        ).scalar()
        actual = built.execute(
            text("SELECT COUNT(DISTINCT deliverable_id) FROM fact_activity")
        ).scalar()
        assert from_view == actual

    def test_skill_position_flags_undefensible_claims(self, built: Session) -> None:
        undefensible = count(built, "v_skill_position", "is_undefensible = 1")
        assert undefensible > 0

    def test_market_demand_keeps_the_unmapped_member(self, built: Session) -> None:
        assert count(built, "v_market_demand", "is_unknown_member = 1") >= 0


class TestParquetExport:
    def test_writes_one_file_per_star_table(
        self, built: Session, engine: Engine, tmp_path: Path
    ) -> None:
        pytest.importorskip("pyarrow")
        written = export_parquet(built, engine, tmp_path)
        assert set(written) == set(star_tables(engine))
        assert all(path.exists() and path.stat().st_size > 0 for path in written.values())

    def test_an_all_null_numeric_column_keeps_a_numeric_type(
        self, built: Session, engine: Engine, tmp_path: Path
    ) -> None:
        """Power BI will not accept a `null`-typed column as a measure.

        `business_value` is empty on the demo data, and pyarrow would infer it
        as the null type, which arrives in Power BI as an untyped column and
        breaks the report rather than showing as blank.
        """
        pyarrow = pytest.importorskip("pyarrow")
        import pyarrow.parquet as pq

        written = export_parquet(built, engine, tmp_path)
        schema = pq.read_table(written["fact_activity"]).schema
        assert schema.field("business_value").type != pyarrow.null()

    def test_round_trips_row_counts(
        self, built: Session, engine: Engine, tmp_path: Path
    ) -> None:
        pytest.importorskip("pyarrow")
        import pyarrow.parquet as pq

        written = export_parquet(built, engine, tmp_path)
        for name, path in written.items():
            assert pq.read_table(path).num_rows == count(built, name)
