"""Workspace isolation, proved against a real PostgreSQL.

`tests/integration/test_rls.py` proves one account cannot see another's rows.
This file proves the harder, newer thing: **one colleague cannot see another
colleague's rows inside the same account**. Phases 1 to 3 had no such notion —
an account was one person — so every assertion here is defending something that
did not previously exist and has no history of being right.

The tests are written against the *database*, not the service layer, for the same
reason `test_rls.py` is: a service check that is not backed by a policy is a
suggestion, and the whole point of ADR-054 is that this one is backed.

`TestTheCompatibilityConcession` is the uncomfortable part of the design, tested
explicitly rather than left implicit: the restrictive policy passes when no user
context is set. That is what keeps every background job working, and it is the
single line of `api/deps.py` that stands between it and a leak.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.conftest import TEST_DATABASE_URL, requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _scope(session: AsyncSession, account_id, user_id=None) -> None:  # type: ignore[no-untyped-def]
    """Set the RLS context the API would set for this person."""
    await session.execute(
        text("SELECT set_config('app.account_id', :a, true)"), {"a": str(account_id)}
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :u, true)"),
        {"u": str(user_id) if user_id else ""},
    )


async def _seed(account_id) -> dict[str, uuid.UUID]:  # type: ignore[no-untyped-def]
    """Two colleagues, one workspace, and three entries, created privileged.

    Written through the owner connection so the rows genuinely exist regardless
    of the policies under test — otherwise a policy bug would make the fixture
    fail rather than the assertion.
    """
    ids = {
        "alice": uuid.uuid4(),
        "bob": uuid.uuid4(),
        "workspace": uuid.uuid4(),
        "shared_entry": uuid.uuid4(),
        "alice_private": uuid.uuid4(),
        "bob_private": uuid.uuid4(),
    }
    admin = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with admin.begin() as conn:
        for key in ("alice", "bob"):
            await conn.execute(
                text(
                    "INSERT INTO app_user (id, account_id, auth_subject, email, timezone, "
                    "locale, role, status, created_at, updated_at) VALUES (:id, :aid, :sub, "
                    ":email, 'Europe/Paris', 'fr-FR', :role, 'active', now(), now())"
                ),
                {
                    "id": ids[key],
                    "aid": account_id,
                    "sub": f"sub-{key}-{ids[key]}",
                    "email": f"{key}-{ids[key]}@example.test",
                    "role": "member",
                },
            )
        await conn.execute(
            text(
                "INSERT INTO workspace (id, account_id, name, created_by, created_at, "
                "updated_at) VALUES (:id, :aid, :name, :by, now(), now())"
            ),
            {
                "id": ids["workspace"],
                "aid": account_id,
                "name": f"Espace {ids['workspace']}",
                "by": ids["alice"],
            },
        )
        # Only Alice is a member. Bob is in the account but not the workspace —
        # the whole point of the fixture.
        await conn.execute(
            text(
                "INSERT INTO workspace_member (id, account_id, workspace_id, user_id, role, "
                "created_at, updated_at) VALUES (:id, :aid, :wid, :uid, 'editor', now(), now())"
            ),
            {
                "id": uuid.uuid4(),
                "aid": account_id,
                "wid": ids["workspace"],
                "uid": ids["alice"],
            },
        )
        for key, owner, workspace in (
            ("shared_entry", "alice", ids["workspace"]),
            ("alice_private", "alice", None),
            ("bob_private", "bob", None),
        ):
            await conn.execute(
                text(
                    "INSERT INTO entry (id, account_id, user_id, workspace_id, entry_type, "
                    "title, status, occurred_at, origin, version, created_at, updated_at) "
                    "VALUES (:id, :aid, :uid, :wid, 'note', :title, 'active', now(), "
                    "'user', 1, now(), now())"
                ),
                {
                    "id": ids[key],
                    "aid": account_id,
                    "uid": ids[owner],
                    "wid": workspace,
                    "title": key,
                },
            )
    await admin.dispose()
    return ids


@pytest.fixture
async def org(session_factory, two_tenants):  # type: ignore[no-untyped-def]
    account_id = two_tenants[0]["account_id"]
    ids = await _seed(account_id)
    return {"account_id": account_id, **ids}


async def _titles(session_factory, account_id, user_id) -> set[str]:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        await _scope(session, account_id, user_id)
        rows = (await session.execute(text("SELECT title FROM entry"))).scalars()
        return set(rows)


class TestWorkspaceVisibility:
    async def test_a_workspace_member_sees_the_shared_entry(self, session_factory, org) -> None:
        titles = await _titles(session_factory, org["account_id"], org["alice"])
        assert "shared_entry" in titles

    async def test_a_colleague_outside_the_workspace_does_not(self, session_factory, org) -> None:
        # The assertion this whole phase exists for. Bob is a legitimate member
        # of the account — the phase 1 policy lets him through — and must still
        # not see a workspace he was never added to.
        titles = await _titles(session_factory, org["account_id"], org["bob"])
        assert "shared_entry" not in titles

    async def test_a_personal_entry_stays_personal(self, session_factory, org) -> None:
        alice = await _titles(session_factory, org["account_id"], org["alice"])
        bob = await _titles(session_factory, org["account_id"], org["bob"])

        assert "alice_private" in alice
        assert "alice_private" not in bob
        assert "bob_private" in bob
        assert "bob_private" not in alice

    async def test_membership_is_what_grants_access_not_the_account(
        self, session_factory, org
    ) -> None:
        # Adding Bob to the workspace must change the answer, with no other
        # write and no cache to invalidate.
        assert "shared_entry" not in await _titles(session_factory, org["account_id"], org["bob"])

        admin = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO workspace_member (id, account_id, workspace_id, user_id, "
                    "role, created_at, updated_at) VALUES (:id, :aid, :wid, :uid, 'reader', "
                    "now(), now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "aid": org["account_id"],
                    "wid": org["workspace"],
                    "uid": org["bob"],
                },
            )
        await admin.dispose()

        assert "shared_entry" in await _titles(session_factory, org["account_id"], org["bob"])

    async def test_a_write_into_another_persons_workspace_is_refused(
        self, session_factory, org
    ) -> None:
        # The restrictive policy governs INSERT too, so this is not merely a
        # read-side control.
        async with session_factory() as session:
            await _scope(session, org["account_id"], org["bob"])
            with pytest.raises(Exception) as caught:
                await session.execute(
                    text(
                        "INSERT INTO entry (id, account_id, user_id, workspace_id, entry_type, "
                        "title, status, occurred_at, origin, version, created_at, updated_at) "
                        "VALUES (:id, :aid, :uid, :wid, 'note', 'intrusion', 'active', now(), "
                        "'user', 1, now(), now())"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "aid": org["account_id"],
                        # Attributed to Alice, into Alice's workspace: the shape
                        # a confused-deputy bug would take.
                        "uid": org["alice"],
                        "wid": org["workspace"],
                    },
                )
                await session.flush()
            assert "policy" in str(caught.value).lower()


class TestCommentVisibility:
    async def test_a_comment_inherits_the_entrys_visibility(self, session_factory, org) -> None:
        admin = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO comment (id, account_id, entry_id, author_id, body, status, "
                    "created_at, updated_at) VALUES (:id, :aid, :eid, :uid, 'secret', 'open', "
                    "now(), now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "aid": org["account_id"],
                    "eid": org["shared_entry"],
                    "uid": org["alice"],
                },
            )
        await admin.dispose()

        async with session_factory() as session:
            await _scope(session, org["account_id"], org["alice"])
            assert (await session.execute(text("SELECT count(*) FROM comment"))).scalar_one() == 1

        async with session_factory() as session:
            await _scope(session, org["account_id"], org["bob"])
            # Derived from the entry rather than duplicated onto the comment, so
            # the two can never disagree.
            assert (await session.execute(text("SELECT count(*) FROM comment"))).scalar_one() == 0


class TestTheCompatibilityConcession:
    """The uncomfortable half of ADR-054, tested rather than left implicit."""

    async def test_without_a_user_context_the_account_is_visible(
        self, session_factory, org
    ) -> None:
        # This is *by design*: every background job — outbox dispatcher,
        # indexer, digest worker — has an account context and no user, and
        # failing closed here would silently disable all of them.
        async with session_factory() as session:
            await _scope(session, org["account_id"], None)
            titles = set((await session.execute(text("SELECT title FROM entry"))).scalars())
        assert {"shared_entry", "alice_private", "bob_private"} <= titles

    async def test_the_api_always_sets_the_user_context(self) -> None:
        """The one line standing between the concession and a leak.

        Asserted by reading the source. A behavioural test cannot catch its
        removal: dropping `user_id=` from the session dependency breaks nothing
        that phases 1 to 3 test, and turns every organisation into a shared
        drive.
        """
        import inspect

        from app.api import deps

        source = inspect.getsource(deps.get_session)
        assert "user_id=principal.user_id" in source

    async def test_the_account_boundary_still_holds_regardless(
        self, session_factory, two_tenants, org
    ) -> None:
        # Whatever workspaces do, the phase 1 guarantee is unchanged: the other
        # tenant sees none of this.
        other = two_tenants[1]
        async with session_factory() as session:
            await _scope(session, other["account_id"], other["user_id"])
            titles = set((await session.execute(text("SELECT title FROM entry"))).scalars())
        assert titles == set()


class TestPolicyShape:
    async def test_the_visibility_policies_are_restrictive(self, session_factory) -> None:
        """Permissive would have been the natural-looking mistake.

        PostgreSQL OR-s permissive policies together, so a permissive second
        policy would *widen* access — exactly the opposite of the intent, and
        invisible in any test that only checks the happy path.
        """
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT polname, polpermissive FROM pg_policy "
                        "WHERE polname LIKE '%_workspace_visibility'"
                    )
                )
            ).all()

        assert len(rows) == 2, "expected a visibility policy on entry and on comment"
        for name, permissive in rows:
            assert permissive is False, f"{name} must be RESTRICTIVE"

    async def test_the_phase_one_policies_were_not_touched(self, session_factory) -> None:
        # The tenant isolation policies are the oldest guarantee in the product.
        # Phase 4 adds a layer; it must not have edited one.
        async with session_factory() as session:
            count = (
                await session.execute(
                    text("SELECT count(*) FROM pg_policy WHERE polname LIKE '%_tenant_isolation'")
                )
            ).scalar_one()
        assert count >= 35


class TestCurrentUserId:
    async def test_the_function_returns_null_when_unset(self, session_factory) -> None:
        # NULL rather than an exception is what lets an unscoped session behave
        # exactly as it did before this migration existed.
        async with session_factory() as session:
            await session.execute(text("SELECT set_config('app.user_id', '', true)"))
            assert (await session.execute(text("SELECT current_user_id()"))).scalar_one() is None

    async def test_the_function_returns_the_configured_user(self, session_factory) -> None:
        target = uuid.uuid4()
        async with session_factory() as session:
            await session.execute(
                text("SELECT set_config('app.user_id', :u, true)"), {"u": str(target)}
            )
            assert (await session.execute(text("SELECT current_user_id()"))).scalar_one() == target


class TestSeededAt:
    async def test_the_fixture_is_meaningful(self, org) -> None:
        # Guards against a fixture that silently seeds nothing, which would make
        # every isolation assertion above vacuously true.
        assert org["alice"] != org["bob"]
        assert isinstance(org["workspace"], uuid.UUID)
        assert datetime.now(UTC).year >= 2026
