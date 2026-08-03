"""Comments, mentions and share links.

The interesting part is not the CRUD, it is the three moments where a naive
implementation quietly does the wrong thing.

**A mention resolves to a person, once, on write.** `@sylvie` is looked up in the
account and stored as a `user_id`. Keeping the raw handle and resolving at render
time means an old comment points at nobody after a rename — or at whoever
inherited the handle, which is worse than nobody.

**A mention only notifies people who can already read the entry.** Mentioning
someone who is not in the workspace would otherwise be a way to leak a title into
their notification centre. They are resolved, stored, and *not* notified; the
comment still renders their name, so the author can see they need to be invited.

**A share link grants exactly what it says.** Following one does not run as the
creator: it opens a scoped read of one entry, and nothing else in the account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collaboration import (
    MAX_COMMENT_LENGTH,
    CommentStatus,
    ShareScope,
    check_share,
    default_expiry,
    handle_for,
    hash_share_token,
    mint_share_token,
    parse_mentions,
)
from app.domain.enums import NotificationKind
from app.domain.errors import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.domain.permissions import Action
from app.infra.db.models.core import AppUser, Entry, Notification
from app.infra.db.models.enterprise import (
    Comment,
    Mention,
    ShareLink,
    Workspace,
    WorkspaceMember,
)
from app.observability.logging import get_logger
from app.services.identity_service import Principal
from app.services.workspace_service import WorkspaceService

log = get_logger("collaboration")


@dataclass(slots=True)
class PostedComment:
    comment: Comment
    mentioned: list[AppUser] = field(default_factory=list)
    # Handles that matched nobody, or matched somebody who cannot read the
    # entry. Returned so the client can show « Paul n'a pas accès à cette
    # note » rather than silently doing nothing.
    unresolved: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IssuedShareLink:
    link: ShareLink
    # Shown once. Only the digest is stored, so a database dump is not a set of
    # live links.
    token: str


class CollaborationService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal
        self._workspaces = WorkspaceService(session, principal=principal)

    # -- Comments ------------------------------------------------------------ #

    async def comment(
        self, entry_id: uuid.UUID, *, body: str, parent_id: uuid.UUID | None = None
    ) -> PostedComment:
        entry = await self._entry(entry_id)
        await self._workspaces.require(Action.COMMENT_WRITE, workspace_id=entry.workspace_id)

        text = body.strip()
        if not text:
            raise ValidationError("Un commentaire ne peut pas être vide.", field="body")
        if len(text) > MAX_COMMENT_LENGTH:
            raise ValidationError(
                f"Un commentaire ne peut pas dépasser {MAX_COMMENT_LENGTH} caractères.",
                field="body",
            )

        if parent_id is not None:
            parent = await self._session.get(Comment, parent_id)
            if parent is None or parent.entry_id != entry_id:
                raise NotFoundError("Commentaire parent introuvable.")
            if parent.parent_id is not None:
                # One level of nesting. Two is a conversation; three is a forum
                # nobody reads to the bottom of.
                raise ValidationError(
                    "Une réponse ne peut pas être commentée à son tour.", field="parent_id"
                )

        comment = Comment(
            account_id=self._principal.account_id,
            entry_id=entry_id,
            author_id=self._principal.user_id,
            parent_id=parent_id,
            body=text,
        )
        self._session.add(comment)
        await self._session.flush()

        mentioned, unresolved = await self._record_mentions(comment, entry)
        log.info(
            "comment.posted",
            entry_id=str(entry_id),
            mentions=len(mentioned),
            unresolved=len(unresolved),
        )
        return PostedComment(comment=comment, mentioned=mentioned, unresolved=unresolved)

    async def _record_mentions(
        self, comment: Comment, entry: Entry
    ) -> tuple[list[AppUser], list[str]]:
        """Resolve handles to people, and notify only those who can read.

        The second half is the one that matters. Notifying somebody about an
        entry they cannot open would leak its title into their notification
        centre — a small leak, delivered by push, to a person who was never
        given access.
        """
        parsed = parse_mentions(comment.body)
        if not parsed:
            return [], []

        candidates = list(
            (
                await self._session.execute(select(AppUser).where(AppUser.deleted_at.is_(None)))
            ).scalars()
        )
        by_handle = {
            handle_for(user.email, display_name=user.display_name): user for user in candidates
        }

        readers = await self._readers_of(entry)
        mentioned: list[AppUser] = []
        unresolved: list[str] = []

        for item in parsed:
            user = by_handle.get(item.handle)
            if user is None:
                unresolved.append(item.handle)
                continue
            if user.id == self._principal.user_id:
                # Mentioning yourself is legitimate in a note to self and must
                # not produce a notification.
                mentioned.append(user)
                continue

            self._session.add(
                Mention(
                    account_id=self._principal.account_id,
                    comment_id=comment.id,
                    user_id=user.id,
                    handle=item.handle,
                    notified_at=datetime.now(UTC) if user.id in readers else None,
                )
            )
            mentioned.append(user)

            if user.id not in readers:
                # Stored but not notified: the name still renders, so the author
                # can see they need to grant access.
                unresolved.append(item.handle)
                continue

            self._session.add(
                Notification(
                    account_id=self._principal.account_id,
                    user_id=user.id,
                    kind=NotificationKind.MENTION.value,
                    title=f"{self._principal.email} vous a mentionné",
                    body=comment.body[:200],
                    entry_id=entry.id,
                )
            )

        await self._session.flush()
        return mentioned, unresolved

    async def _readers_of(self, entry: Entry) -> set[uuid.UUID]:
        """Who may read this entry.

        A personal entry has exactly one reader. A workspace entry has its
        members. Computed rather than assumed, because "everyone in the account"
        is the wrong answer the moment workspaces exist.
        """
        if entry.workspace_id is None:
            return {entry.user_id}
        rows = (
            await self._session.execute(
                select(WorkspaceMember.user_id).where(
                    WorkspaceMember.workspace_id == entry.workspace_id
                )
            )
        ).scalars()
        return set(rows) | {entry.user_id}

    async def list_comments(self, entry_id: uuid.UUID) -> list[Comment]:
        entry = await self._entry(entry_id)
        await self._workspaces.require(Action.COMMENT_READ, workspace_id=entry.workspace_id)
        return list(
            (
                await self._session.execute(
                    select(Comment)
                    .where(Comment.entry_id == entry_id, Comment.deleted_at.is_(None))
                    .order_by(Comment.created_at)
                )
            ).scalars()
        )

    async def edit_comment(self, comment_id: uuid.UUID, *, body: str) -> Comment:
        comment = await self._comment(comment_id)
        if comment.author_id != self._principal.user_id:
            # Editing somebody else's words is not a permission any role has.
            # An administrator may delete a comment; nobody may rewrite one.
            raise PermissionDeniedError("Vous ne pouvez modifier que vos propres commentaires.")

        text = body.strip()
        if not text:
            raise ValidationError("Un commentaire ne peut pas être vide.", field="body")

        comment.body = text[:MAX_COMMENT_LENGTH]
        comment.edited_at = datetime.now(UTC)

        # Mentions are re-derived: adding a name in an edit must notify them,
        # removing one must not leave a dangling row.
        await self._session.execute(delete(Mention).where(Mention.comment_id == comment.id))
        entry = await self._entry(comment.entry_id)
        await self._record_mentions(comment, entry)
        return comment

    async def delete_comment(self, comment_id: uuid.UUID) -> Comment:
        comment = await self._comment(comment_id)
        entry = await self._entry(comment.entry_id)

        if comment.author_id != self._principal.user_id:
            await self._workspaces.require(
                Action.COMMENT_DELETE_ANY, workspace_id=entry.workspace_id
            )

        # Soft delete, so a reply below it does not become an answer to nothing.
        comment.deleted_at = datetime.now(UTC)
        comment.status = CommentStatus.DELETED.value
        await self._session.flush()
        return comment

    async def resolve_comment(self, comment_id: uuid.UUID, *, resolved: bool = True) -> Comment:
        comment = await self._comment(comment_id)
        entry = await self._entry(comment.entry_id)
        await self._workspaces.require(Action.COMMENT_WRITE, workspace_id=entry.workspace_id)

        comment.resolved_at = datetime.now(UTC) if resolved else None
        comment.resolved_by = self._principal.user_id if resolved else None
        comment.status = (CommentStatus.RESOLVED if resolved else CommentStatus.OPEN).value
        await self._session.flush()
        return comment

    # -- Mentions ------------------------------------------------------------ #

    async def my_mentions(self, *, unread_only: bool = False) -> list[Mention]:
        stmt = (
            select(Mention)
            .where(Mention.user_id == self._principal.user_id)
            .order_by(Mention.created_at.desc())
            .limit(100)
        )
        if unread_only:
            stmt = stmt.where(Mention.read_at.is_(None))
        return list((await self._session.execute(stmt)).scalars())

    async def mark_mention_read(self, mention_id: uuid.UUID) -> Mention:
        mention = await self._session.get(Mention, mention_id)
        if mention is None or mention.user_id != self._principal.user_id:
            raise NotFoundError("Mention introuvable.")
        mention.read_at = datetime.now(UTC)
        await self._session.flush()
        return mention

    # -- Share links --------------------------------------------------------- #

    async def share_entry(
        self,
        entry_id: uuid.UUID,
        *,
        expires_at: datetime | None = None,
        allow_comments: bool = False,
    ) -> IssuedShareLink:
        entry = await self._entry(entry_id)
        await self._workspaces.require(Action.SHARE_CREATE, workspace_id=entry.workspace_id)

        token = mint_share_token()
        link = ShareLink(
            account_id=self._principal.account_id,
            scope=ShareScope.ENTRY.value,
            entry_id=entry_id,
            token_hash=token.digest,
            token_suffix=token.suffix,
            created_by=self._principal.user_id,
            # Expiring by default is the decision. A link pasted into a chat two
            # years ago should not still open.
            expires_at=expires_at or default_expiry(datetime.now(UTC)),
            allow_comments=allow_comments,
        )
        self._session.add(link)
        await self._session.flush()
        log.info("share.created", entry_id=str(entry_id), scope="entry")
        return IssuedShareLink(link=link, token=token.plaintext)

    async def list_shares(self) -> list[ShareLink]:
        return list(
            (
                await self._session.execute(
                    select(ShareLink)
                    .where(ShareLink.revoked_at.is_(None))
                    .order_by(ShareLink.created_at.desc())
                )
            ).scalars()
        )

    async def revoke_share(self, link_id: uuid.UUID) -> ShareLink:
        link = await self._session.get(ShareLink, link_id)
        if link is None:
            raise NotFoundError("Lien introuvable.")
        await self._workspaces.require(Action.SHARE_REVOKE)
        # Revoked, not deleted: a link nobody can explain afterwards is an audit
        # gap.
        link.revoked_at = datetime.now(UTC)
        await self._session.flush()
        return link

    # -- Helpers ------------------------------------------------------------- #

    async def _entry(self, entry_id: uuid.UUID) -> Entry:
        entry = (
            await self._session.execute(
                select(Entry).where(Entry.id == entry_id, Entry.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if entry is None:
            # Also the answer when the restrictive policy hid it. A 404 rather
            # than a 403 on purpose: telling someone an entry exists but is not
            # theirs is itself a disclosure.
            raise NotFoundError("Note introuvable.")
        return entry

    async def _comment(self, comment_id: uuid.UUID) -> Comment:
        comment = (
            await self._session.execute(
                select(Comment).where(Comment.id == comment_id, Comment.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if comment is None:
            raise NotFoundError("Commentaire introuvable.")
        return comment


async def resolve_share_link(session: AsyncSession, *, token: str) -> ShareLink:
    """Open a share link. Runs on a privileged session, deliberately.

    The visitor has no account, so there is no tenant context to set — and
    setting the *creator's* context would hand a stranger a session scoped to
    the whole account. Instead the link is resolved on a maintenance connection
    and the caller may read exactly the one entry it names.
    """
    digest = hash_share_token(token)
    link = (
        await session.execute(select(ShareLink).where(ShareLink.token_hash == digest))
    ).scalar_one_or_none()
    if link is None:
        raise NotFoundError("Lien introuvable.")

    validity = check_share(
        revoked_at=link.revoked_at, expires_at=link.expires_at, now=datetime.now(UTC)
    )
    if not validity.valid:
        raise PermissionDeniedError(validity.reason)

    link.view_count += 1
    link.last_viewed_at = datetime.now(UTC)
    await session.flush()
    return link


async def shared_entry(session: AsyncSession, link: ShareLink) -> Entry:
    """The single entry a link exposes.

    Scoped by id rather than by tenant context: following a link must not be a
    way to run queries as the account.
    """
    if link.entry_id is None:
        raise NotFoundError("Ce lien ne pointe pas vers une note.")
    entry = (
        await session.execute(
            select(Entry).where(Entry.id == link.entry_id, Entry.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("La note partagée n'existe plus.")
    return entry


async def workspace_summary(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    """Counts for the administration screen."""
    workspaces = (
        await session.execute(
            select(func.count())
            .select_from(Workspace)
            .where(Workspace.account_id == account_id, Workspace.archived_at.is_(None))
        )
    ).scalar_one()
    members = (
        await session.execute(
            select(func.count())
            .select_from(AppUser)
            .where(AppUser.account_id == account_id, AppUser.deleted_at.is_(None))
        )
    ).scalar_one()
    shared = (
        await session.execute(
            select(func.count())
            .select_from(ShareLink)
            .where(
                ShareLink.account_id == account_id,
                ShareLink.revoked_at.is_(None),
                or_(ShareLink.expires_at.is_(None), ShareLink.expires_at > datetime.now(UTC)),
            )
        )
    ).scalar_one()
    return {
        "workspaces": int(workspaces),
        "members": int(members),
        "active_share_links": int(shared),
    }
