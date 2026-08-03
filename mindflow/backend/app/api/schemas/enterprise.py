"""Request and response shapes for the enterprise layer (API.md §16).

Two shapes carry a decision rather than merely data.

`ShareLinkView.token` is present in exactly one response — the creation one —
and null everywhere else. The plaintext is never stored, so it can never be
shown again. A schema that returned it on every read would be a schema that
required storing it.

`CommentView.unresolved_mentions` exists so the client can say « Paul n'a pas
accès à cette note ». Mentioning somebody into a workspace they are not in
resolves and stores the mention but sends no notification; telling the author is
the difference between a rule and a silent failure.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Workspaces
# --------------------------------------------------------------------------- #
class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=9)


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=9)
    archived: bool | None = None


class WorkspaceView(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    color: str | None = None
    archived: bool = False
    created_at: datetime


class MemberView(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    role: str
    role_label: str
    # None when the member is not in the workspace being listed — or when the
    # listing is account-wide. The two are distinguished by the endpoint, never
    # conflated in the payload.
    workspace_role: str | None = None


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: str = Field(default="editor", pattern="^(editor|commenter|reader)$")


class SetRoleRequest(BaseModel):
    role: str = Field(pattern="^(owner|admin|member|viewer)$")


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="member", pattern="^(owner|admin|member|viewer)$")
    workspace_id: uuid.UUID | None = None


class InvitationView(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    workspace_id: uuid.UUID | None = None
    # Present once, in the creation response, so the caller can build the link.
    token: str | None = None
    expires_at: datetime
    created_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)


# --------------------------------------------------------------------------- #
# Collaboration
# --------------------------------------------------------------------------- #
class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: uuid.UUID | None = None


class CommentView(BaseModel):
    id: uuid.UUID
    entry_id: uuid.UUID
    author_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    body: str
    status: str
    resolved: bool = False
    edited: bool = False
    created_at: datetime
    mentioned_user_ids: list[uuid.UUID] = Field(default_factory=list)
    # Handles that matched nobody, or matched somebody who cannot read the
    # entry. The client says so rather than the mention failing silently.
    unresolved_mentions: list[str] = Field(default_factory=list)


class MentionView(BaseModel):
    id: uuid.UUID
    comment_id: uuid.UUID
    handle: str
    read: bool = False
    created_at: datetime


class ShareRequest(BaseModel):
    expires_at: datetime | None = None
    allow_comments: bool = False


class ShareLinkView(BaseModel):
    id: uuid.UUID
    scope: str
    entry_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    # Exactly one response carries this. Only the digest is stored, so it can
    # never be shown again — which is the point.
    token: str | None = None
    token_suffix: str
    expires_at: datetime | None = None
    revoked: bool = False
    view_count: int = 0
    created_at: datetime


class SharedEntryView(BaseModel):
    """What an unauthenticated visitor sees. One entry, nothing else."""

    entry_id: uuid.UUID
    title: str
    body: str | None = None
    entry_type: str
    occurred_at: datetime
    allow_comments: bool = False
    expires_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Integrations
# --------------------------------------------------------------------------- #
class ConnectRequest(BaseModel):
    provider: str = Field(
        pattern="^(google_calendar|outlook_calendar|microsoft_todo|slack|teams|notion|obsidian)$"
    )
    access_token: str = Field(min_length=1)
    refresh_token: str | None = None
    expires_at: datetime | None = None
    label: str | None = Field(default=None, max_length=255)
    # Never `two_way` by default. It is the setting most likely to surprise
    # somebody by writing into their calendar.
    direction: str = Field(default="pull", pattern="^(pull|push|two_way)$")
    settings: dict[str, Any] = Field(default_factory=dict)


class ConnectionView(BaseModel):
    id: uuid.UUID
    provider: str
    label: str
    account_label: str | None = None
    status: str
    direction: str
    # False for Obsidian. Surfaced so the client can explain why there is no
    # "sync now" button rather than showing one that does nothing.
    server_side: bool = True
    last_sync_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0

    @property
    def needs_attention(self) -> bool:
        return self.status in ("expired", "error")


class SyncReportView(BaseModel):
    provider: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    conflicts: int = 0
    # True with a 200: a provider outage is not a client error, and turning it
    # into a 4xx would make a retry loop out of what the scheduler handles.
    failed: bool = False
    reason: str = ""


class ConflictView(BaseModel):
    id: uuid.UUID
    provider: str
    entry_id: uuid.UUID | None = None
    external_url: str | None = None
    detected_at: datetime


class ResolveConflictRequest(BaseModel):
    keep: str = Field(pattern="^(local|remote)$")
