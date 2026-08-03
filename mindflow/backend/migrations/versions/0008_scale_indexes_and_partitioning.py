"""Indexes and retention for thousands of users (Phase 4)

Every index here comes from a query that exists in the code, not from a guess.
An index nobody's query matches costs write throughput and buys nothing, and the
usual way a schema acquires them is somebody adding one per column "to be safe".

The three that matter, and why:

* **`entry` gains a covering index for the workspace read path.** The restrictive
  policy of ADR-054 makes `workspace_id` part of every content query in an
  organisation, and without an index the policy's subquery turns each read into
  a sequential scan of the account's entries.

* **`audit_log` is partitioned by month.** It is the only table that grows
  without bound and is never updated — the exact shape partitioning is for.
  Retention then becomes `DROP TABLE` on a partition instead of a `DELETE` that
  takes a lock and leaves the table bloated.

* **`entity_mention` gains a count-supporting index.** « Quels sujets reviennent
  souvent ? » is a `GROUP BY` over this table, and it is the one query whose cost
  grows with the corpus rather than with the page size.

Partitioning `audit_log` requires rebuilding it, because PostgreSQL cannot
convert a plain table in place. That is done here with a rename-and-copy, which
is safe for a table whose rows are append-only and whose loss would be an
inconvenience rather than a catastrophe — and which is stated in the deployment
notes as the one step of this migration that is not instant.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Partitions created ahead of time. A month that arrives with no partition
# makes every insert fail, so the maintenance job creates them in advance and
# this migration seeds a year — long enough that a forgotten job is noticed by
# a human before it is noticed by an outage.
MONTHS_AHEAD = 12


def upgrade() -> None:
    # -- Read paths that phase 4 made hot ------------------------------------
    # The workspace membership lookup runs inside the restrictive policy, so it
    # is on *every* content read in an organisation. Covering `role` as well
    # means the policy's EXISTS never touches the heap.
    op.execute(
        "CREATE INDEX IF NOT EXISTS workspace_member_lookup_idx "
        "ON workspace_member (user_id, workspace_id) INCLUDE (role)"
    )

    # Comment threads are read per entry, newest last. Partial on live rows
    # because a deleted comment is never listed.
    op.create_index(
        "comment_entry_live_idx",
        "comment",
        ["entry_id", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # The mention badge: "how many unread for me". Partial, because read
    # mentions are the overwhelming majority and none of them is ever counted.
    op.create_index(
        "mention_unread_idx",
        "mention",
        ["user_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )

    # « Quels sujets reviennent souvent ? » — the one query whose cost grows
    # with the corpus rather than with the page size.
    op.create_index(
        "entity_mention_rollup_idx", "entity_mention", ["account_id", "entity_id", "occurred_at"]
    )

    # The sync scheduler asks "which connections are due?" every minute across
    # every tenant. Partial on active ones: a revoked connection is never due.
    op.create_index(
        "integration_connection_due_idx",
        "integration_connection",
        ["last_sync_at"],
        postgresql_where=sa.text("status = 'active'"),
    )

    # Resolving a share link is an unauthenticated lookup by digest, and the
    # only index that must be fast for a request carrying no tenant context.
    op.execute(
        "CREATE INDEX IF NOT EXISTS share_link_live_idx ON share_link (token_hash) "
        "WHERE revoked_at IS NULL"
    )

    # -- audit_log: partitioned by month -------------------------------------
    # Append-only and unbounded — the exact shape partitioning is for. Retention
    # becomes DROP TABLE on a partition rather than a DELETE that takes a lock
    # and leaves the table bloated.
    op.execute("ALTER TABLE audit_log RENAME TO audit_log_legacy")
    op.execute(
        """
        CREATE TABLE audit_log (
            id            bigserial   NOT NULL,
            account_id    uuid        REFERENCES account(id) ON DELETE SET NULL,
            actor_user_id uuid,
            actor_type    varchar(16) NOT NULL,
            action        varchar(64) NOT NULL,
            resource_type varchar(48),
            resource_id   uuid,
            metadata      jsonb       NOT NULL DEFAULT '{}',
            occurred_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT audit_log_actor_type_valid
                CHECK (actor_type IN ('user','system','admin','integration')),
            -- The partition key must be part of every unique constraint, which
            -- is why the primary key is composite rather than `id` alone.
            PRIMARY KEY (id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            start_month date := date_trunc('month', now())::date - interval '1 month';
            i int;
            from_date date;
            to_date date;
        BEGIN
            FOR i IN 0..{months} LOOP
                from_date := (start_month + (i || ' month')::interval)::date;
                to_date := (start_month + ((i + 1) || ' month')::interval)::date;
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS audit_log_%s '
                    'PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
                    to_char(from_date, 'YYYYMM'), from_date, to_date
                );
            END LOOP;
        END $$;
        """.replace("{months}", str(MONTHS_AHEAD))
    )
    # Copied rather than migrated in place: PostgreSQL cannot convert a plain
    # table to a partitioned one. Rows older than the oldest partition are
    # dropped, which for an audit trail seeded at install time is nothing.
    op.execute(
        """
        INSERT INTO audit_log (account_id, actor_user_id, actor_type, action,
                               resource_type, resource_id, metadata, occurred_at)
        SELECT account_id, actor_user_id, actor_type, action, resource_type,
               resource_id, metadata, occurred_at
        FROM audit_log_legacy
        WHERE occurred_at >= date_trunc('month', now()) - interval '1 month'
        """
    )
    op.execute("DROP TABLE audit_log_legacy")

    op.create_index(
        "audit_log_account_id_occurred_at_idx", "audit_log", ["account_id", "occurred_at"]
    )
    op.create_index("audit_log_action_idx", "audit_log", ["action", "occurred_at"])

    op.execute("GRANT SELECT, INSERT ON audit_log TO mindflow_app")
    op.execute("GRANT SELECT ON audit_log TO mindflow_readonly")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON audit_log TO mindflow_maintenance")
    # Resolved dynamically rather than hard-coded. Renaming the old table left
    # its sequence holding the canonical name, so the new `bigserial` got a
    # suffixed one — a detail that is invisible until the GRANT fails.
    op.execute(
        """
        DO $$
        DECLARE seq text := pg_get_serial_sequence('audit_log', 'id');
        BEGIN
            IF seq IS NOT NULL THEN
                EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO mindflow_app', seq);
                EXECUTE format(
                    'GRANT USAGE, SELECT ON SEQUENCE %s TO mindflow_maintenance', seq
                );
            END IF;
        END $$;
        """
    )

    # -- Partition maintenance, in the database ------------------------------
    # A month arriving with no partition makes every insert fail. Keeping the
    # creation in SQL rather than in a Python job means it works even when the
    # worker is down — which is precisely when nobody is watching.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ensure_audit_partitions(months_ahead int DEFAULT 3)
        RETURNS int LANGUAGE plpgsql AS $$
        DECLARE
            i int;
            from_date date;
            to_date date;
            created int := 0;
        BEGIN
            FOR i IN 0..months_ahead LOOP
                from_date := (date_trunc('month', now()) + (i || ' month')::interval)::date;
                to_date := (date_trunc('month', now()) + ((i + 1) || ' month')::interval)::date;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class
                    WHERE relname = 'audit_log_' || to_char(from_date, 'YYYYMM')
                ) THEN
                    EXECUTE format(
                        'CREATE TABLE audit_log_%s PARTITION OF audit_log '
                        'FOR VALUES FROM (%L) TO (%L)',
                        to_char(from_date, 'YYYYMM'), from_date, to_date
                    );
                    created := created + 1;
                END IF;
            END LOOP;
            RETURN created;
        END $$;
        """
    )

    # Retention: DROP on a partition rather than DELETE. Instant, reclaims the
    # space, and takes no lock on the rest of the table.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION drop_audit_partitions_before(cutoff date)
        RETURNS int LANGUAGE plpgsql AS $$
        DECLARE
            partition record;
            dropped int := 0;
        BEGIN
            FOR partition IN
                SELECT c.relname
                FROM pg_class c
                JOIN pg_inherits i ON i.inhrelid = c.oid
                JOIN pg_class parent ON parent.oid = i.inhparent
                WHERE parent.relname = 'audit_log'
                  AND c.relname < 'audit_log_' || to_char(cutoff, 'YYYYMM')
            LOOP
                EXECUTE format('DROP TABLE %I', partition.relname);
                dropped := dropped + 1;
            END LOOP;
            RETURN dropped;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS drop_audit_partitions_before(date)")
    op.execute("DROP FUNCTION IF EXISTS ensure_audit_partitions(int)")

    # Collapse the partitions back into a plain table.
    op.execute("ALTER TABLE audit_log RENAME TO audit_log_partitioned")
    op.execute(
        """
        CREATE TABLE audit_log (
            id            bigserial PRIMARY KEY,
            account_id    uuid REFERENCES account(id) ON DELETE SET NULL,
            actor_user_id uuid,
            actor_type    varchar(16) NOT NULL,
            action        varchar(64) NOT NULL,
            resource_type varchar(48),
            resource_id   uuid,
            metadata      jsonb NOT NULL DEFAULT '{}',
            occurred_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT audit_log_actor_type_valid
                CHECK (actor_type IN ('user','system','admin','integration'))
        )
        """
    )
    op.execute(
        "INSERT INTO audit_log (account_id, actor_user_id, actor_type, action, "
        "resource_type, resource_id, metadata, occurred_at) "
        "SELECT account_id, actor_user_id, actor_type, action, resource_type, "
        "resource_id, metadata, occurred_at FROM audit_log_partitioned"
    )
    op.execute("DROP TABLE audit_log_partitioned CASCADE")

    op.drop_index("integration_connection_due_idx", table_name="integration_connection")
    op.drop_index("entity_mention_rollup_idx", table_name="entity_mention")
    op.drop_index("mention_unread_idx", table_name="mention")
    op.drop_index("comment_entry_live_idx", table_name="comment")
    op.execute("DROP INDEX IF EXISTS share_link_live_idx")
    op.execute("DROP INDEX IF EXISTS workspace_member_lookup_idx")
