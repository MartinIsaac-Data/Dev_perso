"""Enterprise endpoints: workspaces, members, comments, sharing, integrations
(API.md §16).

Two things about this router are deliberate and easy to miss.

**`GET /v1/shared/{token}` is the only unauthenticated route in the product.**
It resolves a share link on a maintenance connection and returns exactly the one
entry the link names. It does *not* run as the creator — handing a stranger a
session scoped to somebody's whole account is how "share a note" becomes "share
an account".

**A forbidden action returns `permission_denied`, not `insufficient_scope`.**
They mean different things to a client: a scope problem is solved by
re-authenticating, a role problem is solved by asking an administrator. Sending
the same code for both makes the client offer the wrong remedy.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Query, status

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope
from app.api.schemas.enterprise import (
    AcceptInvitationRequest,
    AddMemberRequest,
    AuthorisationView,
    CallbackRequest,
    CommentRequest,
    CommentView,
    ConflictView,
    ConnectionView,
    ConnectRequest,
    CreateWorkspaceRequest,
    InvitationView,
    InviteRequest,
    MemberView,
    MentionView,
    ResolveConflictRequest,
    SetRoleRequest,
    SharedEntryView,
    ShareLinkView,
    ShareRequest,
    SyncReportView,
    UpdateWorkspaceRequest,
    WorkspaceView,
)
from app.domain.collaboration import ShareScope
from app.domain.errors import NotFoundError
from app.domain.permissions import Role, WorkspaceRole
from app.domain.sync import Direction, Provider
from app.infra.db.models.enterprise import (
    Comment,
    ExternalLink,
    IntegrationConnection,
    Invitation,
    Mention,
    ShareLink,
    Workspace,
)
from app.infra.db.session import privileged_session
from app.services.collaboration_service import (
    CollaborationService,
    resolve_share_link,
    shared_entry,
)
from app.services.integration_service import IntegrationService, SyncReport
from app.services.workspace_service import MemberView as MemberRow
from app.services.workspace_service import WorkspaceService

router = APIRouter(responses=ERROR_RESPONSES)


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def _workspace_view(workspace: Workspace) -> WorkspaceView:
    return WorkspaceView(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        color=workspace.color,
        archived=workspace.archived_at is not None,
        created_at=workspace.created_at,
    )


def _member_view(row: MemberRow) -> MemberView:
    return MemberView(
        user_id=row.user.id,
        email=row.user.email,
        display_name=row.user.display_name,
        role=row.role.value,
        role_label=row.role.label,
        workspace_role=row.workspace_role.value if row.workspace_role else None,
    )


def _comment_view(comment: Comment) -> CommentView:
    return CommentView(
        id=comment.id,
        entry_id=comment.entry_id,
        author_id=comment.author_id,
        parent_id=comment.parent_id,
        body=comment.body,
        status=comment.status,
        resolved=comment.resolved_at is not None,
        edited=comment.edited_at is not None,
        created_at=comment.created_at,
    )


def _share_view(link: ShareLink, *, token: str | None = None) -> ShareLinkView:
    return ShareLinkView(
        id=link.id,
        scope=link.scope,
        entry_id=link.entry_id,
        workspace_id=link.workspace_id,
        # Present exactly once, in the creation response. Only the digest is
        # stored, so it can never be shown again — which is the point.
        token=token,
        token_suffix=link.token_suffix,
        expires_at=link.expires_at,
        revoked=link.revoked_at is not None,
        view_count=link.view_count,
        created_at=link.created_at,
    )


def _provider(value: str) -> Provider:
    """Le fournisseur nommé dans le chemin, ou un 404.

    Un nom inconnu est une adresse qui n'existe pas, pas une donnée invalide :
    `/v1/integrations/dropbox/authorize` ne désigne rien.
    """
    try:
        return Provider(value)
    except ValueError as exc:
        raise NotFoundError(f"Fournisseur inconnu : {value}.") from exc


def _connection_view(connection: IntegrationConnection) -> ConnectionView:
    provider = Provider(connection.provider)
    return ConnectionView(
        id=connection.id,
        provider=connection.provider,
        label=provider.label,
        account_label=connection.external_account_label,
        status=connection.status,
        direction=connection.direction,
        server_side=provider.is_server_side,
        last_sync_at=connection.last_sync_at,
        last_error=connection.last_error,
        consecutive_failures=connection.consecutive_failures,
    )


def _report_view(report: SyncReport) -> SyncReportView:
    return SyncReportView(
        provider=report.provider,
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        deleted=report.deleted,
        conflicts=report.conflicts,
        failed=report.failed,
        reason=report.reason,
    )


def _invitation_view(invitation: Invitation, *, token: str | None = None) -> InvitationView:
    return InvitationView(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        workspace_id=invitation.workspace_id,
        token=token,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


# --------------------------------------------------------------------------- #
# Workspaces
# --------------------------------------------------------------------------- #
@router.get("/workspaces", response_model=Collection[WorkspaceView], summary="Lister les espaces")
async def list_workspaces(
    session: SessionDep,
    principal: PrincipalDep,
    include_archived: Annotated[bool, Query()] = False,
) -> Collection[WorkspaceView]:
    service = WorkspaceService(session, principal=principal)
    rows = await service.list_workspaces(include_archived=include_archived)
    return Collection(data=[_workspace_view(row) for row in rows])


@router.post(
    "/workspaces",
    response_model=Envelope[WorkspaceView],
    status_code=status.HTTP_201_CREATED,
    summary="Créer un espace",
)
async def create_workspace(
    session: SessionDep,
    principal: PrincipalDep,
    payload: Annotated[CreateWorkspaceRequest, Body()],
) -> Envelope[WorkspaceView]:
    service = WorkspaceService(session, principal=principal)
    workspace = await service.create(
        name=payload.name, description=payload.description, color=payload.color
    )
    return Envelope(data=_workspace_view(workspace))


@router.patch(
    "/workspaces/{workspace_id}",
    response_model=Envelope[WorkspaceView],
    summary="Modifier un espace",
)
async def update_workspace(
    session: SessionDep,
    principal: PrincipalDep,
    workspace_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[UpdateWorkspaceRequest, Body()],
) -> Envelope[WorkspaceView]:
    service = WorkspaceService(session, principal=principal)
    workspace = await service.update(
        workspace_id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        archived=payload.archived,
    )
    return Envelope(data=_workspace_view(workspace))


@router.delete(
    "/workspaces/{workspace_id}",
    response_model=Envelope[dict[str, Any]],
    summary="Supprimer un espace",
)
async def delete_workspace(
    session: SessionDep, principal: PrincipalDep, workspace_id: Annotated[uuid.UUID, Path()]
) -> Envelope[dict[str, Any]]:
    """Delete a workspace. Its entries are returned to their authors.

    The count is reported rather than being a silent side effect: an
    administrator tidying up the workspace list deserves to know that fourteen
    notes just became personal again.
    """
    service = WorkspaceService(session, principal=principal)
    freed = await service.delete(workspace_id)
    return Envelope(data={"entries_returned_to_authors": freed})


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=Collection[MemberView],
    summary="Membres d'un espace",
)
async def workspace_members(
    session: SessionDep, principal: PrincipalDep, workspace_id: Annotated[uuid.UUID, Path()]
) -> Collection[MemberView]:
    service = WorkspaceService(session, principal=principal)
    return Collection(data=[_member_view(row) for row in await service.members(workspace_id)])


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=Envelope[MemberView],
    summary="Ajouter un membre à un espace",
)
async def add_workspace_member(
    session: SessionDep,
    principal: PrincipalDep,
    workspace_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[AddMemberRequest, Body()],
) -> Envelope[MemberView]:
    service = WorkspaceService(session, principal=principal)
    await service.add_member(
        workspace_id, user_id=payload.user_id, role=WorkspaceRole(payload.role)
    )
    members = await service.members(workspace_id)
    row = next(member for member in members if member.user.id == payload.user_id)
    return Envelope(data=_member_view(row))


@router.delete(
    "/workspaces/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retirer un membre d'un espace",
)
async def remove_workspace_member(
    session: SessionDep,
    principal: PrincipalDep,
    workspace_id: Annotated[uuid.UUID, Path()],
    user_id: Annotated[uuid.UUID, Path()],
) -> None:
    service = WorkspaceService(session, principal=principal)
    await service.remove_member(workspace_id, user_id=user_id)


# --------------------------------------------------------------------------- #
# Account membership
# --------------------------------------------------------------------------- #
@router.get("/members", response_model=Collection[MemberView], summary="Membres du compte")
async def account_members(session: SessionDep, principal: PrincipalDep) -> Collection[MemberView]:
    service = WorkspaceService(session, principal=principal)
    return Collection(data=[_member_view(row) for row in await service.account_members()])


@router.patch(
    "/members/{user_id}/role", response_model=Envelope[MemberView], summary="Changer un rôle"
)
async def set_member_role(
    session: SessionDep,
    principal: PrincipalDep,
    user_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[SetRoleRequest, Body()],
) -> Envelope[MemberView]:
    service = WorkspaceService(session, principal=principal)
    user = await service.set_role(user_id, role=Role(payload.role))
    return Envelope(
        data=MemberView(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            role_label=Role(user.role).label,
        )
    )


@router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retirer un membre du compte",
)
async def remove_member(
    session: SessionDep, principal: PrincipalDep, user_id: Annotated[uuid.UUID, Path()]
) -> None:
    service = WorkspaceService(session, principal=principal)
    await service.remove_member_from_account(user_id)


@router.get(
    "/invitations", response_model=Collection[InvitationView], summary="Invitations en attente"
)
async def list_invitations(
    session: SessionDep, principal: PrincipalDep
) -> Collection[InvitationView]:
    service = WorkspaceService(session, principal=principal)
    return Collection(data=[_invitation_view(row) for row in await service.pending_invitations()])


@router.post(
    "/invitations",
    response_model=Envelope[InvitationView],
    status_code=status.HTTP_201_CREATED,
    summary="Inviter quelqu'un",
)
async def invite(
    session: SessionDep,
    principal: PrincipalDep,
    payload: Annotated[InviteRequest, Body()],
) -> Envelope[InvitationView]:
    """Invite by email.

    The token is returned once so the caller can build the link. Re-inviting the
    same address refreshes the existing invitation instead of stacking a second:
    four live links for one person means accepting the oldest can grant a role
    that was subsequently downgraded.
    """
    service = WorkspaceService(session, principal=principal)
    issued = await service.invite(
        email=payload.email,
        role=Role(payload.role),
        workspace_id=payload.workspace_id,
    )
    return Envelope(data=_invitation_view(issued.invitation, token=issued.token))


@router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Révoquer une invitation",
)
async def revoke_invitation(
    session: SessionDep, principal: PrincipalDep, invitation_id: Annotated[uuid.UUID, Path()]
) -> None:
    service = WorkspaceService(session, principal=principal)
    await service.revoke_invitation(invitation_id)


# --------------------------------------------------------------------------- #
# Comments and mentions
# --------------------------------------------------------------------------- #
@router.get(
    "/entries/{entry_id}/comments",
    response_model=Collection[CommentView],
    summary="Commentaires d'une note",
)
async def list_comments(
    session: SessionDep, principal: PrincipalDep, entry_id: Annotated[uuid.UUID, Path()]
) -> Collection[CommentView]:
    service = CollaborationService(session, principal=principal)
    return Collection(data=[_comment_view(row) for row in await service.list_comments(entry_id)])


@router.post(
    "/entries/{entry_id}/comments",
    response_model=Envelope[CommentView],
    status_code=status.HTTP_201_CREATED,
    summary="Commenter une note",
)
async def post_comment(
    session: SessionDep,
    principal: PrincipalDep,
    entry_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[CommentRequest, Body()],
) -> Envelope[CommentView]:
    """Post a comment. Mentions are resolved and, where allowed, notified.

    `unresolved_mentions` carries the handles that matched nobody *or* matched
    somebody who cannot read the entry. The client shows « Paul n'a pas accès à
    cette note » rather than silently doing nothing — mentioning someone into a
    workspace they are not in must not leak the title into their notifications.
    """
    service = CollaborationService(session, principal=principal)
    posted = await service.comment(entry_id, body=payload.body, parent_id=payload.parent_id)
    view = _comment_view(posted.comment)
    view.unresolved_mentions = posted.unresolved
    view.mentioned_user_ids = [user.id for user in posted.mentioned]
    return Envelope(data=view)


@router.patch(
    "/comments/{comment_id}",
    response_model=Envelope[CommentView],
    summary="Modifier un commentaire",
)
async def edit_comment(
    session: SessionDep,
    principal: PrincipalDep,
    comment_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[CommentRequest, Body()],
) -> Envelope[CommentView]:
    service = CollaborationService(session, principal=principal)
    return Envelope(data=_comment_view(await service.edit_comment(comment_id, body=payload.body)))


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un commentaire",
)
async def delete_comment(
    session: SessionDep, principal: PrincipalDep, comment_id: Annotated[uuid.UUID, Path()]
) -> None:
    service = CollaborationService(session, principal=principal)
    await service.delete_comment(comment_id)


@router.post(
    "/comments/{comment_id}/resolve",
    response_model=Envelope[CommentView],
    summary="Marquer un fil comme résolu",
)
async def resolve_comment(
    session: SessionDep,
    principal: PrincipalDep,
    comment_id: Annotated[uuid.UUID, Path()],
    resolved: Annotated[bool, Query()] = True,
) -> Envelope[CommentView]:
    service = CollaborationService(session, principal=principal)
    return Envelope(
        data=_comment_view(await service.resolve_comment(comment_id, resolved=resolved))
    )


@router.get("/mentions", response_model=Collection[MentionView], summary="Mes mentions")
async def my_mentions(
    session: SessionDep,
    principal: PrincipalDep,
    unread_only: Annotated[bool, Query()] = False,
) -> Collection[MentionView]:
    service = CollaborationService(session, principal=principal)
    rows: list[Mention] = await service.my_mentions(unread_only=unread_only)
    return Collection(
        data=[
            MentionView(
                id=row.id,
                comment_id=row.comment_id,
                handle=row.handle,
                read=row.read_at is not None,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.post(
    "/mentions/{mention_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marquer une mention comme lue",
)
async def read_mention(
    session: SessionDep, principal: PrincipalDep, mention_id: Annotated[uuid.UUID, Path()]
) -> None:
    service = CollaborationService(session, principal=principal)
    await service.mark_mention_read(mention_id)


# --------------------------------------------------------------------------- #
# Sharing
# --------------------------------------------------------------------------- #
@router.post(
    "/entries/{entry_id}/share",
    response_model=Envelope[ShareLinkView],
    status_code=status.HTTP_201_CREATED,
    summary="Créer un lien de partage",
)
async def share_entry(
    session: SessionDep,
    principal: PrincipalDep,
    entry_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[ShareRequest, Body()],
) -> Envelope[ShareLinkView]:
    """Mint a read link. The token is returned exactly once.

    Links expire by default (thirty days). A link pasted into a chat two years
    ago should not still open, and making expiry opt-out rather than opt-in is
    the difference between a product that is safe by default and one that is
    safe when somebody remembers.
    """
    service = CollaborationService(session, principal=principal)
    issued = await service.share_entry(
        entry_id, expires_at=payload.expires_at, allow_comments=payload.allow_comments
    )
    return Envelope(data=_share_view(issued.link, token=issued.token))


@router.get("/shares", response_model=Collection[ShareLinkView], summary="Liens actifs")
async def list_shares(session: SessionDep, principal: PrincipalDep) -> Collection[ShareLinkView]:
    service = CollaborationService(session, principal=principal)
    return Collection(data=[_share_view(link) for link in await service.list_shares()])


@router.delete(
    "/shares/{link_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Révoquer un lien"
)
async def revoke_share(
    session: SessionDep, principal: PrincipalDep, link_id: Annotated[uuid.UUID, Path()]
) -> None:
    service = CollaborationService(session, principal=principal)
    await service.revoke_share(link_id)


@router.get(
    "/shared/{token}",
    response_model=Envelope[SharedEntryView],
    summary="Ouvrir un lien partagé",
    # No authentication. The only such route in the product.
    responses=ERROR_RESPONSES,
)
async def open_shared(
    token: Annotated[str, Path(min_length=16, max_length=128)],
) -> Envelope[SharedEntryView]:
    """Follow a share link, without an account.

    Runs on a maintenance connection because the visitor has no tenant context —
    and setting the *creator's* context would hand a stranger a session scoped
    to the whole account. What comes back is one entry, by id, and nothing else.
    """
    async with privileged_session() as session:
        link = await resolve_share_link(session, token=token)
        entry = await shared_entry(session, link)
        return Envelope(
            data=SharedEntryView(
                entry_id=entry.id,
                title=entry.title,
                body=entry.body,
                entry_type=entry.entry_type,
                occurred_at=entry.occurred_at,
                allow_comments=link.allow_comments,
                expires_at=link.expires_at,
            )
        )


# --------------------------------------------------------------------------- #
# Integrations
# --------------------------------------------------------------------------- #
@router.get("/integrations", response_model=Collection[ConnectionView], summary="Mes intégrations")
async def list_integrations(
    session: SessionDep, principal: PrincipalDep, settings: SettingsDep
) -> Collection[ConnectionView]:
    service = IntegrationService(session, principal=principal, settings=settings)
    return Collection(data=[_connection_view(row) for row in await service.list_connections()])


@router.post(
    "/integrations",
    response_model=Envelope[ConnectionView],
    status_code=status.HTTP_201_CREATED,
    summary="Connecter un service",
)
async def connect_integration(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    payload: Annotated[ConnectRequest, Body()],
) -> Envelope[ConnectionView]:
    """Store an authorised grant, after the OAuth exchange.

    The tokens arrive in plaintext and are encrypted before they touch a row
    (ADR-058). They are never returned, by this endpoint or any other.
    """
    service = IntegrationService(session, principal=principal, settings=settings)
    connection = await service.connect(
        provider=Provider(payload.provider),
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        expires_at=payload.expires_at,
        label=payload.label,
        direction=Direction(payload.direction),
        settings=payload.settings,
    )
    return Envelope(data=_connection_view(connection))


@router.get(
    "/integrations/{provider}/authorize",
    response_model=Envelope[AuthorisationView],
    summary="Démarrer une autorisation OAuth",
)
async def authorize_integration(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    provider: str,
) -> Envelope[AuthorisationView]:
    """L'adresse du consentement, et le `state` à renvoyer avec le code.

    Rien n'est stocké entre cet appel et le retour : le vérificateur PKCE et
    l'identité du demandeur voyagent chiffrés dans le `state` (ADR-064).
    """
    service = IntegrationService(session, principal=principal, settings=settings)
    request = service.begin_authorisation(_provider(provider))
    return Envelope(
        data=AuthorisationView(
            provider=request.provider.value,
            authorize_url=request.url,
            state=request.state,
        )
    )


@router.post(
    "/integrations/{provider}/callback",
    response_model=Envelope[ConnectionView],
    status_code=status.HTTP_201_CREATED,
    summary="Terminer une autorisation OAuth",
)
async def complete_integration(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    provider: str,
    payload: Annotated[CallbackRequest, Body()],
) -> Envelope[ConnectionView]:
    """Échange le code contre des jetons, puis enregistre la connexion.

    Le fournisseur effectif vient du `state`, pas du chemin : c'est le `state`
    qui est authentifié.
    """
    _provider(provider)
    service = IntegrationService(session, principal=principal, settings=settings)
    connection = await service.complete_authorisation(
        code=payload.code,
        state=payload.state,
        label=payload.label,
        direction=Direction(payload.direction),
        settings=payload.settings,
    )
    return Envelope(data=_connection_view(connection))


@router.delete(
    "/integrations/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Déconnecter un service",
)
async def disconnect_integration(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    connection_id: Annotated[uuid.UUID, Path()],
) -> None:
    service = IntegrationService(session, principal=principal, settings=settings)
    await service.disconnect(connection_id)


@router.post(
    "/integrations/{connection_id}/sync",
    response_model=Envelope[SyncReportView],
    summary="Synchroniser maintenant",
)
async def sync_now(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    connection_id: Annotated[uuid.UUID, Path()],
) -> Envelope[SyncReportView]:
    """Run one pass on demand.

    Returns 200 even when the provider failed, with `failed` and `reason` set.
    A provider outage is not a client error, and turning it into a 4xx would
    make a retry loop out of something the scheduler already handles.
    """
    service = IntegrationService(session, principal=principal, settings=settings)
    return Envelope(data=_report_view(await service.sync(connection_id)))


@router.get(
    "/integrations/conflicts",
    response_model=Collection[ConflictView],
    summary="Conflits de synchronisation",
)
async def list_conflicts(
    session: SessionDep, principal: PrincipalDep, settings: SettingsDep
) -> Collection[ConflictView]:
    """Items changed on both sides since the last sync.

    Surfaced rather than resolved. Last-write-wins would silently discard
    whichever version the user cared about.
    """
    service = IntegrationService(session, principal=principal, settings=settings)
    rows: list[ExternalLink] = await service.conflicts()
    return Collection(
        data=[
            ConflictView(
                id=row.id,
                provider=row.provider,
                entry_id=row.entry_id,
                external_url=row.external_url,
                detected_at=row.conflict_at or datetime.now(),
            )
            for row in rows
        ]
    )


@router.post(
    "/integrations/conflicts/{link_id}/resolve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Trancher un conflit",
)
async def resolve_conflict(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    link_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[ResolveConflictRequest, Body()],
) -> None:
    service = IntegrationService(session, principal=principal, settings=settings)
    await service.resolve_conflict(link_id, keep=payload.keep)


# --------------------------------------------------------------------------- #
# Invitation acceptance
# --------------------------------------------------------------------------- #
@router.post(
    "/invitations/accept",
    response_model=Envelope[dict[str, Any]],
    summary="Accepter une invitation",
)
async def accept(
    session: SessionDep,
    principal: PrincipalDep,
    payload: Annotated[AcceptInvitationRequest, Body()],
) -> Envelope[dict[str, Any]]:
    """Claim an invitation.

    The caller is authenticated but is *not yet* a member of the account they
    are joining, so this runs on a privileged session — a tenant-scoped one
    would be scoped to the wrong tenant, and would see no invitation at all.
    """
    from app.infra.db.models.core import AppUser
    from app.services.workspace_service import accept_invitation

    async with privileged_session() as elevated:
        user = await elevated.get(AppUser, principal.user_id)
        if user is None:
            raise NotFoundError("Utilisateur introuvable.")
        invitation = await accept_invitation(elevated, token=payload.token, user=user)
        return Envelope(
            data={
                "account_id": str(invitation.account_id),
                "role": invitation.role,
                "workspace_id": str(invitation.workspace_id) if invitation.workspace_id else None,
            }
        )


__all__ = ["ShareScope", "router"]
