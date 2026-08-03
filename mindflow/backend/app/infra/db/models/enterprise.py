"""Tables for the enterprise layer (Phase 4): workspaces, membership, comments,
mentions, share links, integrations.

**The account is the organisation.** That is the decision this whole file rests
on. `app_user.account_id` already allowed several people per account, so the
tenant boundary — and every RLS policy written since phase 1 — is untouched. An
organisation is an `account` with `kind = 'org'`.

The alternative was a new `organisation` level above `account`. It would have
meant rewriting `current_account_id()`, re-deriving thirty-two RLS policies, and
re-verifying an isolation guarantee that currently has a table-by-table test
proving it. All to express something the existing shape already expressed.

**Workspace visibility is a second, restrictive layer** (ADR-054). The permissive
policy `account_id = current_account_id()` stays exactly as it was; a restrictive
policy is AND-ed on top for the tables that carry workspace-scoped content.
Restrictive rather than permissive is the whole trick: a second permissive policy
would *widen* access, which is the opposite of what is wanted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.models.base import Base, TimestampMixin, uuid_pk


class Workspace(Base, TimestampMixin):
    """A container of shared content inside an account.

    Nullable everywhere it is referenced: an entry with no workspace is
    *personal*, which is the phase 1 behaviour and remains the default. Making
    workspaces mandatory would have forced a migration of every existing row
    into a synthetic "default workspace" — a rewrite of working data to satisfy
    a new abstraction.
    """

    __tablename__ = "workspace"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    # Shown in lists; the same palette as projects, so the two read as one
    # visual system rather than two.
    color: Mapped[str | None] = mapped_column(String(9))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("account_id", "name", name="workspace_account_id_name_unique"),
        Index("workspace_account_id_idx", "account_id"),
    )


class WorkspaceMember(Base, TimestampMixin):
    """Who is in a workspace, and with what standing.

    This table is what the restrictive RLS policy consults. It is therefore on
    the read path of every single content query, which is why the index on
    (user_id, workspace_id) exists and why the policy's subquery is written to
    hit it.
    """

    __tablename__ = "workspace_member"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(16), default="editor", server_default="editor", nullable=False
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))

    __table_args__ = (
        CheckConstraint("role IN ('editor','commenter','reader')", name="role_valid"),
        UniqueConstraint(
            "workspace_id", "user_id", name="workspace_member_workspace_id_user_id_unique"
        ),
        # Ordered (user, workspace) rather than (workspace, user): the hot query
        # is "which workspaces may this person see", asked on every content read.
        Index("workspace_member_user_id_workspace_id_idx", "user_id", "workspace_id"),
    )


class Invitation(Base, TimestampMixin):
    """A pending invitation to an account.

    Keyed by email rather than by user, because the invitee has no account yet —
    that is the point of an invitation. Resolution to a real user happens on
    acceptance, when they authenticate.
    """

    __tablename__ = "invitation"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), default="member", server_default="member", nullable=False
    )
    # Optional: an invitation may seat someone directly into a workspace.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("role IN ('owner','admin','member','viewer')", name="role_valid"),
        # One live invitation per address. Re-inviting refreshes rather than
        # stacking, so accepting the oldest of four links cannot grant a role
        # that was subsequently downgraded.
        # Partial: only *pending* rows participate. A revoked or accepted
        # invitation must not block re-inviting the same address, which is the
        # ordinary case when somebody rejoins.
        Index(
            "invitation_account_id_email_unique",
            "account_id",
            "email",
            unique=True,
            postgresql_where=sql_text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        Index("invitation_token_hash_idx", "token_hash"),
    )


class Comment(Base, TimestampMixin):
    """A remark on an entry.

    Threaded one level deep — a reply may not itself be replied to. Two levels
    is a conversation; three is a forum nobody reads to the bottom of.
    """

    __tablename__ = "comment"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comment.id", ondelete="CASCADE")
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open", nullable=False
    )
    # Soft delete: a removed comment leaves a tombstone so a reply below it does
    # not become an answer to nothing.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('open','resolved','deleted')", name="status_valid"),
        # A reply to a reply is refused at the database, not merely discouraged
        # in the service — see migration 0007 for the trigger-free formulation.
        Index("comment_entry_id_created_at_idx", "entry_id", "created_at"),
        Index("comment_parent_id_idx", "parent_id"),
    )


class Mention(Base):
    """Somebody named in a comment.

    Resolved at write time to a `user_id`, never left as raw text. A handle
    resolved at render time points at nobody once the person is renamed, or at
    whoever inherited the handle — which is worse.
    """

    __tablename__ = "mention"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comment.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    # The handle as written, kept so the comment can be re-rendered exactly as
    # typed even after the person's address changes.
    handle: Mapped[str] = mapped_column(String(64), nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="mention_comment_id_user_id_unique"),
        Index("mention_user_id_read_at_idx", "user_id", "read_at"),
    )


class ShareLink(Base, TimestampMixin):
    """A capability to read something without being a member."""

    __tablename__ = "share_link"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE")
    )

    # SHA-256 of the token. The plaintext is shown once, to the creator, and
    # never stored: a database dump must not be a set of live links.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_suffix: Mapped[str] = mapped_column(String(8), nullable=False)

    created_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Revoked rather than deleted: a link nobody can explain afterwards is an
    # audit gap.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allow_comments: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )

    __table_args__ = (
        CheckConstraint("scope IN ('entry','workspace')", name="scope_valid"),
        CheckConstraint(
            "(entry_id IS NOT NULL) <> (workspace_id IS NOT NULL)", name="one_target_only"
        ),
        Index("share_link_account_id_idx", "account_id"),
    )


class IntegrationConnection(Base, TimestampMixin):
    """An authorised link to an external service.

    One row per (account, user, provider). Per *user*, not per account: an
    OAuth grant is personal, and a connection made by someone who then leaves
    must stop working rather than silently keep syncing on their behalf.

    Tokens are stored encrypted at rest by the application (`app.infra.crypto`),
    not merely by the disk. A database backup restored to a laptop must not be a
    set of live Google credentials.
    """

    __tablename__ = "integration_connection"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    external_account_id: Mapped[str | None] = mapped_column(String(255))
    external_account_label: Mapped[str | None] = mapped_column(String(255))

    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )
    # The direction the user asked for. Two-way is not the default: it is the
    # setting most likely to surprise someone by writing into their calendar.
    direction: Mapped[str] = mapped_column(
        String(16), default="pull", server_default="pull", nullable=False
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    # Provider-issued cursor for incremental sync (Google syncToken, Graph
    # deltaLink). Opaque to us on purpose — decoding it would couple us to a
    # format the provider is free to change.
    sync_cursor: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('google_calendar','outlook_calendar','microsoft_todo',"
            "'slack','teams','notion','obsidian')",
            name="provider_valid",
        ),
        CheckConstraint("status IN ('active','expired','revoked','error')", name="status_valid"),
        CheckConstraint("direction IN ('pull','push','two_way')", name="direction_valid"),
        UniqueConstraint("account_id", "user_id", "provider", name="integration_connection_unique"),
        Index("integration_connection_account_id_idx", "account_id"),
    )


class ExternalLink(Base, TimestampMixin):
    """The correspondence between one of our rows and one of theirs.

    This table is what makes synchronisation idempotent, and it is the piece
    naive integrations omit. Without it, a pull that runs twice creates every
    event twice, and a push that retries after a timeout creates a second copy
    in the user's calendar — the failure everybody has experienced from the
    receiving end.

    `external_etag` is what makes it *incremental*: an unchanged remote object
    is skipped without a write.
    """

    __tablename__ = "external_link"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_connection.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    external_etag: Mapped[str | None] = mapped_column(String(512))
    external_url: Mapped[str | None] = mapped_column(Text)

    # Which side wrote last. Read by the conflict resolver; without it, "who
    # changed this?" is unanswerable and the resolver has to guess.
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_pulled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A conflict the resolver refused to decide. Surfaced to the user rather
    # than resolved by coin toss.
    conflict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_remotely_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "external_id", name="external_link_connection_external_unique"
        ),
        Index("external_link_entry_id_idx", "entry_id"),
        Index("external_link_account_id_provider_idx", "account_id", "provider"),
    )


class MeetingSession(Base, TimestampMixin):
    """A live meeting being transcribed and assisted in real time.

    Separate from `capture` because the lifecycles differ in the way that
    matters: a capture is a finished artefact that gets processed, a meeting
    session is an open window that accumulates. Reusing `capture` would have
    meant a status machine with two disjoint halves.
    """

    __tablename__ = "meeting_session"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="SET NULL")
    )

    title: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        String(16), default="live", server_default="live", nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Appended as partial transcripts arrive. Kept on the session rather than in
    # `transcript` because it is provisional until the meeting closes.
    live_transcript: Mapped[str | None] = mapped_column(Text)
    # Suggestions produced during the meeting: detected actions, questions
    # nobody answered, decisions. Provisional by nature.
    live_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    # The capture this session produced on closing, if any.
    capture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capture.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("status IN ('live','ended','abandoned')", name="status_valid"),
        Index("meeting_session_account_id_status_idx", "account_id", "status"),
    )


# Tenant tables added by phase 4. Appended to `TENANT_TABLES` in `core.py`.
ENTERPRISE_TENANT_TABLES: tuple[str, ...] = (
    "workspace",
    "workspace_member",
    "invitation",
    "comment",
    "mention",
    "share_link",
    "integration_connection",
    "external_link",
    "meeting_session",
)

# Tables carrying workspace-scoped content, which therefore receive the
# restrictive visibility policy of ADR-054 on top of tenant isolation.
WORKSPACE_SCOPED_TABLES: tuple[str, ...] = ("entry", "comment")
