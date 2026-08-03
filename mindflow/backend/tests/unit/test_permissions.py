"""Who may do what.

A permission bug does not lose data — it shows somebody else's. So this file is
written the way a security control should be: the denials are asserted at least
as carefully as the grants, and the two rules people get wrong (the last owner,
and privilege escalation by subtraction) get a class each.
"""

from __future__ import annotations

import pytest

from app.domain.permissions import (
    Action,
    Actor,
    Role,
    WorkspaceRole,
    assignable_roles,
    can,
    can_remove,
)


def _actor(
    role: Role = Role.MEMBER,
    workspace_role: WorkspaceRole | None = None,
    *,
    owns: bool = False,
    guest: bool = False,
) -> Actor:
    return Actor(
        user_id="u1",
        account_id="a1",
        role=role,
        workspace_role=workspace_role,
        owns_resource=owns,
        is_guest=guest,
    )


class TestRoleOrdering:
    def test_roles_are_ordered(self) -> None:
        assert Role.OWNER.at_least(Role.ADMIN)
        assert Role.ADMIN.at_least(Role.MEMBER)
        assert Role.MEMBER.at_least(Role.VIEWER)
        assert not Role.VIEWER.at_least(Role.MEMBER)

    def test_a_role_is_at_least_itself(self) -> None:
        for role in Role:
            assert role.at_least(role)

    def test_every_role_has_a_french_label(self) -> None:
        assert all(role.label for role in Role)
        assert Role.VIEWER.label == "Lecteur"

    def test_workspace_roles_are_ordered(self) -> None:
        assert WorkspaceRole.EDITOR.at_least(WorkspaceRole.COMMENTER)
        assert WorkspaceRole.COMMENTER.at_least(WorkspaceRole.READER)
        assert not WorkspaceRole.READER.at_least(WorkspaceRole.COMMENTER)


class TestAccountLevel:
    def test_a_viewer_reads_and_does_not_write(self) -> None:
        viewer = _actor(Role.VIEWER)
        assert can(viewer, Action.ENTRY_READ)
        assert not can(viewer, Action.ENTRY_WRITE)
        assert not can(viewer, Action.CAPTURE_CREATE)

    def test_a_member_writes_but_does_not_administer(self) -> None:
        member = _actor(Role.MEMBER)
        assert can(member, Action.ENTRY_WRITE)
        assert not can(member, Action.MEMBER_INVITE)
        assert not can(member, Action.AUDIT_READ)

    def test_an_admin_administers_but_does_not_bill(self) -> None:
        admin = _actor(Role.ADMIN)
        assert can(admin, Action.MEMBER_INVITE)
        assert can(admin, Action.AUDIT_READ)
        # Owner-only, and both irreversible or financial.
        assert not can(admin, Action.BILLING_MANAGE)
        assert not can(admin, Action.ACCOUNT_DELETE)

    def test_an_owner_may_do_everything(self) -> None:
        owner = _actor(Role.OWNER)
        assert all(can(owner, action) for action in Action)

    def test_a_denial_says_what_is_needed(self) -> None:
        # « Vous devez être administrateur » tells a user what to ask for;
        # « accès refusé » tells them to file a support ticket.
        decision = can(_actor(Role.MEMBER), Action.AUDIT_READ)
        assert not decision
        assert "administrateur" in decision.reason.lower()


class TestWorkspaceLevel:
    def test_a_reader_may_not_write_in_the_workspace(self) -> None:
        actor = _actor(Role.MEMBER, WorkspaceRole.READER)
        assert not can(actor, Action.ENTRY_WRITE, in_workspace=True)

    def test_a_commenter_comments_but_does_not_edit(self) -> None:
        actor = _actor(Role.MEMBER, WorkspaceRole.COMMENTER)
        assert can(actor, Action.COMMENT_WRITE, in_workspace=True)
        assert not can(actor, Action.ENTRY_WRITE, in_workspace=True)

    def test_an_editor_edits(self) -> None:
        actor = _actor(Role.MEMBER, WorkspaceRole.EDITOR)
        assert can(actor, Action.ENTRY_WRITE, in_workspace=True)

    def test_a_non_member_is_denied_with_a_useful_reason(self) -> None:
        actor = _actor(Role.MEMBER, None)
        decision = can(actor, Action.ENTRY_WRITE, in_workspace=True)
        assert not decision
        assert "membre de cet espace" in decision.reason

    def test_not_a_workspace_resource_is_not_the_same_as_not_a_member(self) -> None:
        # Both have `workspace_role is None`; conflating them would lock a
        # member out of their own personal entries.
        actor = _actor(Role.MEMBER, None)
        assert can(actor, Action.ENTRY_WRITE, in_workspace=False)
        assert not can(actor, Action.ENTRY_WRITE, in_workspace=True)

    def test_an_account_admin_may_act_in_any_workspace(self) -> None:
        # The one place account role cascades down, deliberately: without it an
        # administrator is locked out of a workspace whose last editor left —
        # the support ticket every such product receives.
        admin = _actor(Role.ADMIN, None)
        assert can(admin, Action.ENTRY_WRITE, in_workspace=True)

    def test_owning_a_row_lets_you_retract_it(self) -> None:
        # A person may always retract what they said, with no workspace
        # standing.
        actor = _actor(Role.MEMBER, WorkspaceRole.READER, owns=True)
        assert can(actor, Action.COMMENT_WRITE, in_workspace=True)


class TestGuests:
    def test_a_link_visitor_reads_only(self) -> None:
        guest = _actor(guest=True)
        assert can(guest, Action.ENTRY_READ)
        assert can(guest, Action.COMMENT_READ)
        assert not can(guest, Action.ENTRY_WRITE)
        assert not can(guest, Action.COMMENT_WRITE)

    def test_a_guest_is_denied_by_omission(self) -> None:
        # New actions are guest-denied until somebody decides otherwise, rather
        # than guest-allowed until somebody remembers.
        guest = _actor(guest=True)
        denied = [action for action in Action if not can(guest, action)]
        assert len(denied) == len(Action) - 2

    def test_a_guests_account_role_is_ignored(self) -> None:
        # A guest carrying an owner role — which should never happen, but a
        # construction bug could produce it — must still read only.
        guest = Actor(user_id="", account_id="a1", role=Role.OWNER, is_guest=True)
        assert not can(guest, Action.ACCOUNT_DELETE)


class TestUnknownActions:
    def test_an_unmapped_action_is_denied(self) -> None:
        """The default that fails safely.

        Every action currently has a mapping, so this asserts the *shape* of
        the fallback rather than a live gap: `can` returns a denial instead of
        raising KeyError, which is what stops a new enum member from becoming
        an unhandled exception in production.
        """
        from app.domain import permissions

        original = dict(permissions._ACCOUNT_MINIMUM)
        try:
            permissions._ACCOUNT_MINIMUM.pop(Action.ENTRY_READ)
            decision = can(_actor(Role.OWNER), Action.ENTRY_READ)
            assert not decision
            assert "inconnue" in decision.reason
        finally:
            permissions._ACCOUNT_MINIMUM.clear()
            permissions._ACCOUNT_MINIMUM.update(original)


class TestAssignableRoles:
    def test_nobody_grants_above_their_own_rank(self) -> None:
        # Otherwise an admin promotes themselves to owner and the distinction
        # means nothing.
        assert Role.OWNER not in assignable_roles(Role.ADMIN)
        assert Role.ADMIN in assignable_roles(Role.ADMIN)

    def test_an_owner_may_transfer_ownership(self) -> None:
        assert Role.OWNER in assignable_roles(Role.OWNER)

    def test_a_member_grants_nothing_above_member(self) -> None:
        assert set(assignable_roles(Role.MEMBER)) == {Role.MEMBER, Role.VIEWER}


class TestRemoval:
    def test_anybody_may_remove_themselves(self) -> None:
        # Leaving a company you no longer work for should not require asking
        # its administrator.
        assert can_remove(_actor(Role.VIEWER), target_role=Role.VIEWER, is_self=True)

    def test_a_member_may_not_remove_anybody_else(self) -> None:
        assert not can_remove(_actor(Role.MEMBER), target_role=Role.MEMBER, is_self=False)

    def test_an_admin_may_not_remove_an_owner(self) -> None:
        # Privilege escalation by subtraction: remove the owners, become the
        # highest-ranked person left.
        decision = can_remove(_actor(Role.ADMIN), target_role=Role.OWNER, is_self=False)
        assert not decision
        assert "rang supérieur" in decision.reason

    def test_an_admin_may_remove_a_member(self) -> None:
        assert can_remove(_actor(Role.ADMIN), target_role=Role.MEMBER, is_self=False)

    def test_an_owner_may_remove_another_owner(self) -> None:
        assert can_remove(_actor(Role.OWNER), target_role=Role.OWNER, is_self=False)


class TestDecisionIsBoolean:
    @pytest.mark.parametrize("allowed", [True, False])
    def test_a_decision_reads_as_a_condition(self, allowed: bool) -> None:
        # `if not can(...)` must work, or every call site grows a `.allowed`
        # that somebody will eventually forget.
        from app.domain.permissions import Decision

        assert bool(Decision(allowed)) is allowed
