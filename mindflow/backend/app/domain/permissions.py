"""Who may do what, decided in one place.

Phases 1 to 3 assumed one person per account. `app_user.role` existed and was
barely consulted, because there was never a second person to be protected from.
Enterprise changes that, and the change is the most dangerous of the four phases:
a permission bug does not lose data, it *shows someone else's*.

Three rules shape this module.

**Permissions are computed, never stored.** A `permissions` column on a row would
be a cache of a derivation, and caches of derivations go stale in exactly the
direction that grants access. What is stored is membership and role; what a role
implies lives here, in code, tested.

**The check is a total function.** `can(actor, action, resource)` answers for
every combination rather than raising on the ones nobody thought about. An
unknown combination returns *deny* — the only default that fails safely.

**Two independent layers, and the database owns the outer one.** Account
isolation stays where it has always been: a PostgreSQL RLS policy that no
application bug can bypass (ADR-005). Workspace visibility is a second,
*restrictive* policy (ADR-054). This module is the third layer, and it exists to
give good error messages and to stop actions the database would allow — editing
someone else's comment, for instance, which is a write to a row you can legally
see.

A permission check in application code that has no database policy behind it is a
suggestion, not a control. Everything enforced here is also enforced below.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """A person's standing in an account.

    Deliberately four, not a matrix of toggles. Custom role builders are the
    feature every enterprise product adds and every enterprise administrator
    then misconfigures; four named roles can be reasoned about out loud.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    # Reads everything shared with them, writes nothing. For an auditor, an
    # accountant, an outgoing employee during handover.
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        """Ordering, so comparisons read as `>=` rather than as set membership."""
        return {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}[self]

    def at_least(self, other: Role) -> bool:
        return self.rank >= other.rank

    @property
    def label(self) -> str:
        return {
            Role.OWNER: "Propriétaire",
            Role.ADMIN: "Administrateur",
            Role.MEMBER: "Membre",
            Role.VIEWER: "Lecteur",
        }[self]


class WorkspaceRole(StrEnum):
    """Standing inside one workspace, independent of account role.

    A member of the account can be an editor of one workspace and absent from
    another. Account role does not cascade down — with one exception below.
    """

    EDITOR = "editor"
    COMMENTER = "commenter"
    READER = "reader"

    @property
    def rank(self) -> int:
        return {WorkspaceRole.READER: 0, WorkspaceRole.COMMENTER: 1, WorkspaceRole.EDITOR: 2}[self]

    def at_least(self, other: WorkspaceRole) -> bool:
        return self.rank >= other.rank

    @property
    def label(self) -> str:
        return {
            WorkspaceRole.EDITOR: "Éditeur",
            WorkspaceRole.COMMENTER: "Commentateur",
            WorkspaceRole.READER: "Lecteur",
        }[self]


class Action(StrEnum):
    """Every act the product gates. One flat list on purpose.

    Grouping actions into "modules" is how permission systems acquire a
    resource that belongs to two modules and a check that consults the wrong
    one. A flat enum is longer and never ambiguous.
    """

    # Content
    ENTRY_READ = "entry.read"
    ENTRY_WRITE = "entry.write"
    ENTRY_DELETE = "entry.delete"
    CAPTURE_CREATE = "capture.create"
    # Collaboration
    COMMENT_READ = "comment.read"
    COMMENT_WRITE = "comment.write"
    COMMENT_DELETE_ANY = "comment.delete_any"
    SHARE_CREATE = "share.create"
    SHARE_REVOKE = "share.revoke"
    # Workspaces
    WORKSPACE_READ = "workspace.read"
    WORKSPACE_WRITE = "workspace.write"
    WORKSPACE_DELETE = "workspace.delete"
    WORKSPACE_INVITE = "workspace.invite"
    # Account administration
    MEMBER_INVITE = "member.invite"
    MEMBER_REMOVE = "member.remove"
    MEMBER_SET_ROLE = "member.set_role"
    INTEGRATION_CONNECT = "integration.connect"
    INTEGRATION_DISCONNECT = "integration.disconnect"
    AUDIT_READ = "audit.read"
    ANALYTICS_READ = "analytics.read"
    BILLING_MANAGE = "billing.manage"
    ACCOUNT_DELETE = "account.delete"


# What each account role may do *at the account level*. Workspace-scoped acts
# are resolved separately, below.
_ACCOUNT_MINIMUM: dict[Action, Role] = {
    Action.ENTRY_READ: Role.VIEWER,
    Action.ENTRY_WRITE: Role.MEMBER,
    Action.ENTRY_DELETE: Role.MEMBER,
    Action.CAPTURE_CREATE: Role.MEMBER,
    Action.COMMENT_READ: Role.VIEWER,
    Action.COMMENT_WRITE: Role.MEMBER,
    Action.COMMENT_DELETE_ANY: Role.ADMIN,
    Action.SHARE_CREATE: Role.MEMBER,
    Action.SHARE_REVOKE: Role.MEMBER,
    Action.WORKSPACE_READ: Role.VIEWER,
    Action.WORKSPACE_WRITE: Role.MEMBER,
    Action.WORKSPACE_DELETE: Role.ADMIN,
    Action.WORKSPACE_INVITE: Role.MEMBER,
    Action.MEMBER_INVITE: Role.ADMIN,
    Action.MEMBER_REMOVE: Role.ADMIN,
    Action.MEMBER_SET_ROLE: Role.ADMIN,
    Action.INTEGRATION_CONNECT: Role.MEMBER,
    Action.INTEGRATION_DISCONNECT: Role.MEMBER,
    Action.AUDIT_READ: Role.ADMIN,
    Action.ANALYTICS_READ: Role.ADMIN,
    # Owner-only, both of them irreversible or financial.
    Action.BILLING_MANAGE: Role.OWNER,
    Action.ACCOUNT_DELETE: Role.OWNER,
}

# Acts that additionally require standing *in the workspace* holding the
# resource. Reading is governed by membership itself (and by the restrictive RLS
# policy); these are the writes.
_WORKSPACE_MINIMUM: dict[Action, WorkspaceRole] = {
    Action.ENTRY_WRITE: WorkspaceRole.EDITOR,
    Action.ENTRY_DELETE: WorkspaceRole.EDITOR,
    Action.COMMENT_WRITE: WorkspaceRole.COMMENTER,
    Action.WORKSPACE_WRITE: WorkspaceRole.EDITOR,
    Action.WORKSPACE_INVITE: WorkspaceRole.EDITOR,
    Action.SHARE_CREATE: WorkspaceRole.EDITOR,
}


@dataclass(frozen=True, slots=True)
class Actor:
    """The person asking, and their standing.

    `workspace_role` is None when the resource is not in a workspace — a
    personal entry — or when the actor is not a member of the one that holds it.
    Those two cases are distinguished by the caller, never conflated here.
    """

    user_id: str
    account_id: str
    role: Role
    workspace_role: WorkspaceRole | None = None
    # True when the actor owns the specific row. Ownership grants edit and
    # delete on your own comment without any workspace standing: a person may
    # always retract what they said.
    owns_resource: bool = False
    # Set for a link-shared, unauthenticated visitor. Never an account member.
    is_guest: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role.at_least(Role.ADMIN)


@dataclass(frozen=True, slots=True)
class Decision:
    """Allowed or not, and *why not*.

    The reason is not decoration. « Vous devez être administrateur » tells a
    user what to ask for; « accès refusé » tells them to file a support ticket.
    """

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


ALLOW = Decision(True)


def can(actor: Actor, action: Action, *, in_workspace: bool = False) -> Decision:
    """May this actor perform this action? Never raises.

    `in_workspace` says whether the resource being acted on lives in a
    workspace. It is passed explicitly rather than inferred from
    `actor.workspace_role`, because "not a member" and "not a workspace
    resource" must not produce the same answer — the first is a denial, the
    second is a personal item the actor may well own.
    """
    if actor.is_guest:
        return _guest(action)

    minimum = _ACCOUNT_MINIMUM.get(action)
    if minimum is None:
        # An action nobody mapped. Deny — the only default that fails safely.
        return Decision(False, f"Action inconnue : {action.value}")

    if not actor.role.at_least(minimum):
        return Decision(False, f"Rôle {minimum.label.lower()} requis.")

    if not in_workspace:
        return ALLOW

    needed = _WORKSPACE_MINIMUM.get(action)
    if needed is None:
        return ALLOW

    # Retracting your own words needs no workspace standing.
    if actor.owns_resource and action in (Action.COMMENT_WRITE, Action.ENTRY_WRITE):
        return ALLOW

    # An account admin can act in any workspace of their account. This is the
    # single place account role cascades into a workspace, and it is deliberate:
    # without it, an administrator can be locked out of a workspace whose last
    # editor has left, which is the support ticket every such product receives.
    if actor.is_admin:
        return ALLOW

    if actor.workspace_role is None:
        return Decision(False, "Vous n'êtes pas membre de cet espace.")
    if not actor.workspace_role.at_least(needed):
        return Decision(False, f"Rôle {needed.label.lower()} requis dans cet espace.")
    return ALLOW


def _guest(action: Action) -> Decision:
    """A visitor holding a share link.

    Reading only, and only the two things a shared item consists of. Everything
    else is denied by omission rather than by a list, so a new action is
    guest-denied until somebody decides otherwise.
    """
    if action in (Action.ENTRY_READ, Action.COMMENT_READ):
        return ALLOW
    return Decision(False, "Lien de partage en lecture seule.")


def assignable_roles(actor_role: Role) -> tuple[Role, ...]:
    """Which roles this actor may grant.

    Nobody grants a role above their own — otherwise an admin promotes
    themselves to owner and the distinction means nothing. An owner may grant
    owner, which is how ownership is transferred.
    """
    return tuple(role for role in Role if actor_role.at_least(role))


def can_remove(actor: Actor, *, target_role: Role, is_self: bool) -> Decision:
    """May this actor remove that member?

    Two rules that look like edge cases and are the ones that actually get hit:
    an admin cannot remove an owner (privilege escalation by subtraction), and
    anybody may remove themselves — leaving a company you no longer work for
    should not require asking its administrator.
    """
    if is_self:
        return ALLOW
    if not actor.role.at_least(Role.ADMIN):
        return Decision(False, "Rôle administrateur requis.")
    if not actor.role.at_least(target_role):
        return Decision(False, "Vous ne pouvez pas retirer un membre de rang supérieur.")
    return ALLOW
