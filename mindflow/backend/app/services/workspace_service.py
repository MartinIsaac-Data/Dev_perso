"""Workspaces, membership and invitations.

The service that must not have a bug. Everything below it — comments, sharing,
the assistant's retrieval scope — inherits whatever this decides about who may
see what.

Three properties it holds, each because getting it wrong is a data leak rather
than a malfunction:

**A membership write is checked twice.** Once here, for a good error message,
and once by the database, which is the control that actually matters. An
application check with no policy behind it is a suggestion.

**Removing the last owner is refused.** An account with no owner cannot manage
billing, cannot delete itself and cannot promote anybody — it is an account
nobody can administer, recoverable only by a support engineer with database
access. Refusing is not paternalism; it is refusing to create a state with no
exit.

**An invitation is resolved to a user at acceptance, never at creation.** The
invitee usually has no account yet — that is the point — so the row is keyed by
email and only becomes a membership when somebody authenticates and claims it.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.domain.permissions import Action, Actor, Role, WorkspaceRole, can, can_remove
from app.infra.db.models.core import AppUser, Entry
from app.infra.db.models.enterprise import Invitation, Workspace, WorkspaceMember
from app.observability.logging import get_logger
from app.services.identity_service import Principal

log = get_logger("workspace")

INVITATION_TTL = timedelta(days=14)
MAX_WORKSPACES_PER_ACCOUNT = 200


@dataclass(slots=True)
class MemberView:
    user: AppUser
    role: Role
    workspace_role: WorkspaceRole | None = None


@dataclass(slots=True)
class IssuedInvitation:
    invitation: Invitation
    # Returned exactly once, to the inviter, to be put in a link. Only the
    # digest is stored.
    token: str


class WorkspaceService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    # -- Actor resolution --------------------------------------------------- #

    async def actor(self, *, workspace_id: uuid.UUID | None = None) -> Actor:
        """The caller's standing, optionally within one workspace.

        Resolved from the database on every call rather than cached on the
        principal. A role change must take effect on the next request, not on
        the next login — an administrator revoking access expects it to be
        revoked.
        """
        workspace_role: WorkspaceRole | None = None
        if workspace_id is not None:
            row = (
                await self._session.execute(
                    select(WorkspaceMember.role).where(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.user_id == self._principal.user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                workspace_role = WorkspaceRole(row)

        return Actor(
            user_id=str(self._principal.user_id),
            account_id=str(self._principal.account_id),
            role=Role(self._principal.role),
            workspace_role=workspace_role,
        )

    async def require(
        self, action: Action, *, workspace_id: uuid.UUID | None = None, owns: bool = False
    ) -> Actor:
        """Authorise, or raise with a reason the user can act on."""
        actor = await self.actor(workspace_id=workspace_id)
        if owns:
            actor = Actor(
                user_id=actor.user_id,
                account_id=actor.account_id,
                role=actor.role,
                workspace_role=actor.workspace_role,
                owns_resource=True,
            )
        decision = can(actor, action, in_workspace=workspace_id is not None)
        if not decision:
            raise PermissionDeniedError(decision.reason)
        return actor

    # -- Workspaces --------------------------------------------------------- #

    async def create(
        self, *, name: str, description: str | None = None, color: str | None = None
    ) -> Workspace:
        await self.require(Action.WORKSPACE_WRITE)

        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Le nom de l'espace est obligatoire.", field="name")

        total = (
            await self._session.execute(
                select(func.count()).select_from(Workspace).where(Workspace.archived_at.is_(None))
            )
        ).scalar_one()
        if total >= MAX_WORKSPACES_PER_ACCOUNT:
            raise ValidationError(
                f"Limite de {MAX_WORKSPACES_PER_ACCOUNT} espaces atteinte.", field="name"
            )

        workspace = Workspace(
            account_id=self._principal.account_id,
            name=cleaned[:120],
            description=description,
            color=color,
            created_by=self._principal.user_id,
        )
        self._session.add(workspace)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("Un espace porte déjà ce nom.") from exc

        # The creator is seated as editor immediately. A workspace whose creator
        # cannot see it is the first bug every such feature ships with — and it
        # is invisible to the author, who is usually an admin and therefore
        # exempt from the check that would have caught it.
        self._session.add(
            WorkspaceMember(
                account_id=self._principal.account_id,
                workspace_id=workspace.id,
                user_id=self._principal.user_id,
                role=WorkspaceRole.EDITOR.value,
                added_by=self._principal.user_id,
            )
        )
        await self._session.flush()
        log.info("workspace.created", workspace_id=str(workspace.id))
        return workspace

    async def list_workspaces(self, *, include_archived: bool = False) -> list[Workspace]:
        """The workspaces this caller may see.

        Filtered by membership here as well as by RLS. Belt and braces is the
        right posture: the policy is the control, and this keeps an admin —
        who the policy would let through — from being shown workspaces they
        never joined.
        """
        stmt = (
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == self._principal.user_id)
            .order_by(Workspace.name)
        )
        if not include_archived:
            stmt = stmt.where(Workspace.archived_at.is_(None))
        return list((await self._session.execute(stmt)).scalars())

    async def get(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = await self._session.get(Workspace, workspace_id)
        if workspace is None:
            raise NotFoundError("Espace introuvable.")
        await self.require(Action.WORKSPACE_READ, workspace_id=workspace_id)
        return workspace

    async def update(
        self,
        workspace_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        archived: bool | None = None,
    ) -> Workspace:
        workspace = await self.get(workspace_id)
        await self.require(Action.WORKSPACE_WRITE, workspace_id=workspace_id)

        if name is not None and name.strip():
            workspace.name = name.strip()[:120]
        if description is not None:
            workspace.description = description
        if color is not None:
            workspace.color = color
        if archived is not None:
            workspace.archived_at = datetime.now(UTC) if archived else None
        await self._session.flush()
        return workspace

    async def delete(self, workspace_id: uuid.UUID) -> int:
        """Delete a workspace, returning its entries to their authors.

        The entries are **not** deleted. `entry.workspace_id` is ON DELETE SET
        NULL, so they become personal again. Cascading would mean an
        administrator tidying up the workspace list destroys other people's
        notes — recoverable only from a backup, and only if anybody notices.
        """
        workspace = await self.get(workspace_id)
        await self.require(Action.WORKSPACE_DELETE, workspace_id=workspace_id)

        orphaned = (
            await self._session.execute(
                select(func.count()).select_from(Entry).where(Entry.workspace_id == workspace_id)
            )
        ).scalar_one()

        await self._session.delete(workspace)
        await self._session.flush()
        log.info("workspace.deleted", workspace_id=str(workspace_id), entries_freed=orphaned)
        return int(orphaned)

    # -- Workspace membership ----------------------------------------------- #

    async def add_member(
        self, workspace_id: uuid.UUID, *, user_id: uuid.UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        await self.get(workspace_id)
        await self.require(Action.WORKSPACE_INVITE, workspace_id=workspace_id)

        # The target must already belong to the account. RLS would hide a
        # foreign user anyway, but a 404 here says "no such member" instead of
        # letting a foreign key violation surface as a 500.
        target = await self._session.get(AppUser, user_id)
        if target is None or target.account_id != self._principal.account_id:
            raise NotFoundError("Utilisateur introuvable dans ce compte.")

        existing = (
            await self._session.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.role = role.value
            await self._session.flush()
            return existing

        member = WorkspaceMember(
            account_id=self._principal.account_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role.value,
            added_by=self._principal.user_id,
        )
        self._session.add(member)
        await self._session.flush()
        return member

    async def remove_member(self, workspace_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
        await self.get(workspace_id)
        if user_id != self._principal.user_id:
            await self.require(Action.WORKSPACE_INVITE, workspace_id=workspace_id)

        member = (
            await self._session.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise NotFoundError("Ce membre ne fait pas partie de l'espace.")

        await self._session.delete(member)
        await self._session.flush()

    async def members(self, workspace_id: uuid.UUID) -> list[MemberView]:
        await self.get(workspace_id)
        rows = (
            await self._session.execute(
                select(AppUser, WorkspaceMember.role)
                .join(WorkspaceMember, WorkspaceMember.user_id == AppUser.id)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(AppUser.display_name, AppUser.email)
            )
        ).all()
        return [
            MemberView(user=row[0], role=Role(row[0].role), workspace_role=WorkspaceRole(row[1]))
            for row in rows
        ]

    # -- Account membership -------------------------------------------------- #

    async def account_members(self) -> list[MemberView]:
        rows = list(
            (
                await self._session.execute(
                    select(AppUser)
                    .where(AppUser.deleted_at.is_(None))
                    .order_by(AppUser.display_name, AppUser.email)
                )
            ).scalars()
        )
        return [MemberView(user=user, role=Role(user.role)) for user in rows]

    async def set_role(self, user_id: uuid.UUID, *, role: Role) -> AppUser:
        actor = await self.require(Action.MEMBER_SET_ROLE)

        if not actor.role.at_least(role):
            # Otherwise an admin promotes themselves to owner and the
            # distinction between the two means nothing.
            raise PermissionDeniedError("Vous ne pouvez pas attribuer un rôle supérieur au vôtre.")

        target = await self._session.get(AppUser, user_id)
        if target is None or target.account_id != self._principal.account_id:
            raise NotFoundError("Utilisateur introuvable.")

        if Role(target.role) is Role.OWNER and role is not Role.OWNER:
            await self._assert_not_last_owner(user_id)

        target.role = role.value
        await self._session.flush()
        log.info("member.role_changed", user_id=str(user_id), role=role.value)
        return target

    async def remove_member_from_account(self, user_id: uuid.UUID) -> AppUser:
        target = await self._session.get(AppUser, user_id)
        if target is None or target.account_id != self._principal.account_id:
            raise NotFoundError("Utilisateur introuvable.")

        actor = await self.actor()
        decision = can_remove(
            actor, target_role=Role(target.role), is_self=user_id == self._principal.user_id
        )
        if not decision:
            raise PermissionDeniedError(decision.reason)

        if Role(target.role) is Role.OWNER:
            await self._assert_not_last_owner(user_id)

        # Soft delete: their entries, comments and mentions stay readable. A
        # hard delete would silently rewrite the history of every thread they
        # took part in.
        target.deleted_at = datetime.now(UTC)
        target.status = "deleted"
        await self._session.flush()
        log.info("member.removed", user_id=str(user_id))
        return target

    async def _assert_not_last_owner(self, user_id: uuid.UUID) -> None:
        """An account with no owner has no exit.

        Nobody could manage billing, promote anybody or delete it — a state
        recoverable only by a support engineer with database access.
        """
        remaining = (
            await self._session.execute(
                select(func.count())
                .select_from(AppUser)
                .where(
                    AppUser.role == Role.OWNER.value,
                    AppUser.deleted_at.is_(None),
                    AppUser.id != user_id,
                )
            )
        ).scalar_one()
        if remaining == 0:
            raise ValidationError(
                "Ce compte doit conserver au moins un propriétaire. "
                "Nommez un autre propriétaire avant de continuer.",
                field="role",
            )

    # -- Invitations --------------------------------------------------------- #

    async def invite(
        self,
        *,
        email: str,
        role: Role = Role.MEMBER,
        workspace_id: uuid.UUID | None = None,
    ) -> IssuedInvitation:
        actor = await self.require(Action.MEMBER_INVITE)
        if not actor.role.at_least(role):
            raise PermissionDeniedError("Vous ne pouvez pas inviter à un rôle supérieur au vôtre.")

        address = email.strip().lower()
        if "@" not in address:
            raise ValidationError("Adresse e-mail invalide.", field="email")

        # Re-inviting refreshes rather than stacking. Four live links for one
        # address means accepting the oldest can grant a role that was
        # subsequently downgraded.
        pending = (
            await self._session.execute(
                select(Invitation).where(
                    Invitation.email == address,
                    Invitation.accepted_at.is_(None),
                    Invitation.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        expires = datetime.now(UTC) + INVITATION_TTL

        if pending is not None:
            pending.role = role.value
            pending.workspace_id = workspace_id
            pending.token_hash = digest
            pending.expires_at = expires
            pending.invited_by = self._principal.user_id
            await self._session.flush()
            return IssuedInvitation(invitation=pending, token=token)

        invitation = Invitation(
            account_id=self._principal.account_id,
            email=address,
            role=role.value,
            workspace_id=workspace_id,
            token_hash=digest,
            invited_by=self._principal.user_id,
            expires_at=expires,
        )
        self._session.add(invitation)
        await self._session.flush()
        log.info("invitation.created", email=address, role=role.value)
        return IssuedInvitation(invitation=invitation, token=token)

    async def pending_invitations(self) -> list[Invitation]:
        await self.require(Action.MEMBER_INVITE)
        return list(
            (
                await self._session.execute(
                    select(Invitation)
                    .where(Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))
                    .order_by(Invitation.created_at.desc())
                )
            ).scalars()
        )

    async def revoke_invitation(self, invitation_id: uuid.UUID) -> Invitation:
        await self.require(Action.MEMBER_INVITE)
        invitation = await self._session.get(Invitation, invitation_id)
        if invitation is None:
            raise NotFoundError("Invitation introuvable.")
        invitation.revoked_at = datetime.now(UTC)
        await self._session.flush()
        return invitation


async def accept_invitation(session: AsyncSession, *, token: str, user: AppUser) -> Invitation:
    """Claim an invitation. Runs outside `WorkspaceService` on purpose.

    The acceptor is not yet a member of the account they are joining, so a
    service constructed around their principal would be scoped to the wrong
    tenant. This function is called from a privileged path that has already
    authenticated the person.
    """
    digest = hashlib.sha256(token.encode()).hexdigest()
    invitation = (
        await session.execute(select(Invitation).where(Invitation.token_hash == digest))
    ).scalar_one_or_none()

    if invitation is None:
        raise NotFoundError("Invitation introuvable ou déjà utilisée.")
    if invitation.revoked_at is not None:
        raise ValidationError("Cette invitation a été révoquée.")
    if invitation.accepted_at is not None:
        raise ConflictError("Cette invitation a déjà été acceptée.")
    if invitation.expires_at <= datetime.now(UTC):
        raise ValidationError("Cette invitation a expiré.")
    if user.email.strip().lower() != invitation.email:
        # Address-bound on purpose. A forwarded link must not seat a stranger.
        raise PermissionDeniedError("Cette invitation vise une autre adresse e-mail.")

    user.account_id = invitation.account_id
    user.role = invitation.role
    invitation.accepted_at = datetime.now(UTC)

    if invitation.workspace_id is not None:
        session.add(
            WorkspaceMember(
                account_id=invitation.account_id,
                workspace_id=invitation.workspace_id,
                user_id=user.id,
                role=WorkspaceRole.EDITOR.value,
                added_by=invitation.invited_by,
            )
        )

    await session.flush()
    log.info("invitation.accepted", account_id=str(invitation.account_id))
    return invitation
