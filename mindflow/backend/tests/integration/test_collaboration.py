"""Workspaces, comments, sharing and integrations, through the API.

The isolation guarantees are proved at the database level in
`test_workspaces.py`. This file proves the layer above behaves: the right status
codes, the right errors, and the two behaviours that are product decisions
rather than mechanics — a share link that expires by default, and a mention that
resolves without notifying somebody who cannot read the entry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _entry(client: AsyncClient, headers: dict[str, str], *, title: str = "Note") -> dict:
    response = await client.post(
        "/v1/entries",
        headers=headers,
        json={"entry_type": "note", "title": title, "priority": "normal"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _workspace(client: AsyncClient, headers: dict[str, str], *, name: str) -> dict:
    response = await client.post("/v1/workspaces", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["data"]


class TestWorkspaces:
    async def test_creating_one_seats_the_creator(self, client: AsyncClient, auth_headers) -> None:
        # A workspace whose creator cannot see it is the first bug every such
        # feature ships with — and it is invisible to the author, who is
        # usually an admin and therefore exempt from the check.
        await _workspace(client, auth_headers, name="Direction")

        listing = await client.get("/v1/workspaces", headers=auth_headers)
        assert [row["name"] for row in listing.json()["data"]] == ["Direction"]

    async def test_a_duplicate_name_is_a_conflict(self, client: AsyncClient, auth_headers) -> None:
        await _workspace(client, auth_headers, name="Produit")
        response = await client.post(
            "/v1/workspaces", headers=auth_headers, json={"name": "Produit"}
        )
        assert response.status_code == 409

    async def test_an_empty_name_is_refused(self, client: AsyncClient, auth_headers) -> None:
        response = await client.post("/v1/workspaces", headers=auth_headers, json={"name": "   "})
        assert response.status_code == 422

    async def test_archiving_hides_it_by_default(self, client: AsyncClient, auth_headers) -> None:
        workspace = await _workspace(client, auth_headers, name="Ancien")
        await client.patch(
            f"/v1/workspaces/{workspace['id']}", headers=auth_headers, json={"archived": True}
        )

        assert await _names(client, auth_headers) == []
        assert await _names(client, auth_headers, archived=True) == ["Ancien"]

    async def test_deleting_returns_entries_to_their_authors(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Deleting a workspace must not destroy other people's notes.

        `entry.workspace_id` is ON DELETE SET NULL, so they become personal
        again. Cascading would mean an administrator tidying up the workspace
        list destroys work recoverable only from a backup.
        """
        workspace = await _workspace(client, auth_headers, name="Temporaire")
        response = await client.delete(f"/v1/workspaces/{workspace['id']}", headers=auth_headers)

        assert response.status_code == 200
        assert "entries_returned_to_authors" in response.json()["data"]

        # The entries endpoint still answers — nothing was cascaded away.
        listing = await client.get("/v1/entries", headers=auth_headers)
        assert listing.status_code == 200

    async def test_an_unknown_workspace_is_a_404(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get(f"/v1/workspaces/{uuid.uuid4()}/members", headers=auth_headers)
        assert response.status_code == 404


async def _names(client: AsyncClient, headers: dict[str, str], *, archived: bool = False) -> list:
    response = await client.get(
        f"/v1/workspaces?include_archived={str(archived).lower()}", headers=headers
    )
    return [row["name"] for row in response.json()["data"]]


class TestMembership:
    async def test_the_first_user_is_the_owner(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/members", headers=auth_headers)
        assert response.status_code == 200
        members = response.json()["data"]
        assert len(members) == 1
        assert members[0]["role"] == "owner"
        assert members[0]["role_label"] == "Propriétaire"

    async def test_the_last_owner_cannot_be_demoted(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """An account with no owner has no exit.

        Nobody could manage billing, promote anybody or delete it — a state
        recoverable only by a support engineer with database access.
        """
        members = (await client.get("/v1/members", headers=auth_headers)).json()["data"]
        response = await client.patch(
            f"/v1/members/{members[0]['user_id']}/role",
            headers=auth_headers,
            json={"role": "member"},
        )

        assert response.status_code == 422
        assert "propriétaire" in response.json()["detail"].lower()

    async def test_the_last_owner_cannot_remove_themselves(
        self, client: AsyncClient, auth_headers
    ) -> None:
        members = (await client.get("/v1/members", headers=auth_headers)).json()["data"]
        response = await client.delete(f"/v1/members/{members[0]['user_id']}", headers=auth_headers)
        assert response.status_code == 422


class TestInvitations:
    async def test_inviting_returns_the_token_once(self, client: AsyncClient, auth_headers) -> None:
        response = await client.post(
            "/v1/invitations",
            headers=auth_headers,
            json={"email": "nouveau@example.test", "role": "member"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["token"]
        assert len(data["token"]) > 20

        # And never again: the listing carries no token.
        listing = await client.get("/v1/invitations", headers=auth_headers)
        assert listing.json()["data"][0]["token"] is None

    async def test_reinviting_refreshes_rather_than_stacking(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # Four live links for one address means accepting the oldest can grant
        # a role that was subsequently downgraded.
        for role in ("member", "viewer"):
            await client.post(
                "/v1/invitations",
                headers=auth_headers,
                json={"email": "repeat@example.test", "role": role},
            )

        listing = (await client.get("/v1/invitations", headers=auth_headers)).json()["data"]
        pending = [row for row in listing if row["email"] == "repeat@example.test"]
        assert len(pending) == 1
        assert pending[0]["role"] == "viewer"

    async def test_a_malformed_address_is_refused(self, client: AsyncClient, auth_headers) -> None:
        response = await client.post(
            "/v1/invitations", headers=auth_headers, json={"email": "pas-une-adresse"}
        )
        assert response.status_code == 422

    async def test_an_invitation_can_be_revoked(self, client: AsyncClient, auth_headers) -> None:
        created = await client.post(
            "/v1/invitations", headers=auth_headers, json={"email": "revoke@example.test"}
        )
        invitation_id = created.json()["data"]["id"]

        response = await client.delete(f"/v1/invitations/{invitation_id}", headers=auth_headers)

        assert response.status_code == 204
        listing = (await client.get("/v1/invitations", headers=auth_headers)).json()["data"]
        assert all(row["id"] != invitation_id for row in listing)

    async def test_an_unknown_token_is_a_404(self, client: AsyncClient, auth_headers) -> None:
        response = await client.post(
            "/v1/invitations/accept", headers=auth_headers, json={"token": "x" * 32}
        )
        assert response.status_code == 404


class TestComments:
    async def test_commenting_and_reading_back(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers)
        response = await client.post(
            f"/v1/entries/{entry['id']}/comments",
            headers=auth_headers,
            json={"body": "Il faut valider avant vendredi."},
        )

        assert response.status_code == 201
        listing = await client.get(f"/v1/entries/{entry['id']}/comments", headers=auth_headers)
        assert [row["body"] for row in listing.json()["data"]] == [
            "Il faut valider avant vendredi."
        ]

    async def test_a_reply_to_a_reply_is_refused(self, client: AsyncClient, auth_headers) -> None:
        # One level of nesting. Two is a conversation; three is a forum nobody
        # reads to the bottom of.
        entry = await _entry(client, auth_headers)
        root = (
            await client.post(
                f"/v1/entries/{entry['id']}/comments",
                headers=auth_headers,
                json={"body": "racine"},
            )
        ).json()["data"]
        reply = (
            await client.post(
                f"/v1/entries/{entry['id']}/comments",
                headers=auth_headers,
                json={"body": "réponse", "parent_id": root["id"]},
            )
        ).json()["data"]

        response = await client.post(
            f"/v1/entries/{entry['id']}/comments",
            headers=auth_headers,
            json={"body": "trop profond", "parent_id": reply["id"]},
        )
        assert response.status_code == 422

    async def test_an_unknown_handle_is_reported_not_swallowed(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # The client says « Paul n'a pas accès à cette note » rather than the
        # mention failing silently.
        entry = await _entry(client, auth_headers)
        response = await client.post(
            f"/v1/entries/{entry['id']}/comments",
            headers=auth_headers,
            json={"body": "merci @inconnu.total"},
        )

        assert response.status_code == 201
        assert "inconnu.total" in response.json()["data"]["unresolved_mentions"]

    async def test_an_email_in_a_comment_is_not_a_mention(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _entry(client, auth_headers)
        response = await client.post(
            f"/v1/entries/{entry['id']}/comments",
            headers=auth_headers,
            json={"body": "écrire à contact@acme.com"},
        )
        assert response.json()["data"]["unresolved_mentions"] == []

    async def test_a_deleted_comment_disappears_from_the_thread(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _entry(client, auth_headers)
        comment = (
            await client.post(
                f"/v1/entries/{entry['id']}/comments",
                headers=auth_headers,
                json={"body": "à supprimer"},
            )
        ).json()["data"]

        assert (
            await client.delete(f"/v1/comments/{comment['id']}", headers=auth_headers)
        ).status_code == 204

        listing = await client.get(f"/v1/entries/{entry['id']}/comments", headers=auth_headers)
        assert listing.json()["data"] == []

    async def test_a_thread_can_be_resolved(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers)
        comment = (
            await client.post(
                f"/v1/entries/{entry['id']}/comments",
                headers=auth_headers,
                json={"body": "question"},
            )
        ).json()["data"]

        response = await client.post(f"/v1/comments/{comment['id']}/resolve", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["resolved"] is True

    async def test_commenting_on_an_unknown_entry_is_a_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        response = await client.post(
            f"/v1/entries/{uuid.uuid4()}/comments", headers=auth_headers, json={"body": "x"}
        )
        assert response.status_code == 404


class TestSharing:
    async def test_a_link_is_minted_once_and_opens(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers, title="Note partagée")
        created = await client.post(
            f"/v1/entries/{entry['id']}/share", headers=auth_headers, json={}
        )

        assert created.status_code == 201
        token = created.json()["data"]["token"]
        assert token

        # Unauthenticated: the only such route in the product.
        opened = await client.get(f"/v1/shared/{token}")
        assert opened.status_code == 200
        assert opened.json()["data"]["title"] == "Note partagée"

    async def test_links_expire_by_default(self, client: AsyncClient, auth_headers) -> None:
        # A link pasted into a chat two years ago must not still open. Expiry
        # is opt-out, not opt-in.
        entry = await _entry(client, auth_headers)
        created = await client.post(
            f"/v1/entries/{entry['id']}/share", headers=auth_headers, json={}
        )
        expires = created.json()["data"]["expires_at"]

        assert expires is not None
        assert datetime.fromisoformat(expires) > datetime.now(UTC)

    async def test_the_token_is_never_returned_again(
        self, client: AsyncClient, auth_headers
    ) -> None:
        entry = await _entry(client, auth_headers)
        await client.post(f"/v1/entries/{entry['id']}/share", headers=auth_headers, json={})

        listing = await client.get("/v1/shares", headers=auth_headers)
        row = listing.json()["data"][0]
        assert row["token"] is None
        # Enough to tell two links apart; not enough to reconstruct one.
        assert len(row["token_suffix"]) == 6

    async def test_a_revoked_link_stops_opening(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers)
        created = (
            await client.post(f"/v1/entries/{entry['id']}/share", headers=auth_headers, json={})
        ).json()["data"]

        await client.delete(f"/v1/shares/{created['id']}", headers=auth_headers)

        opened = await client.get(f"/v1/shared/{created['token']}")
        assert opened.status_code == 403
        assert "révoqué" in opened.json()["detail"]

    async def test_an_expired_link_says_expired_not_revoked(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # The two mean different things to the person following the link, and
        # to whoever audits it later.
        entry = await _entry(client, auth_headers)
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        created = (
            await client.post(
                f"/v1/entries/{entry['id']}/share",
                headers=auth_headers,
                json={"expires_at": past},
            )
        ).json()["data"]

        opened = await client.get(f"/v1/shared/{created['token']}")
        assert opened.status_code == 403
        assert "expiré" in opened.json()["detail"]

    async def test_an_unknown_token_is_a_404(self, client: AsyncClient) -> None:
        assert (await client.get(f"/v1/shared/{'z' * 40}")).status_code == 404

    async def test_a_view_is_counted(self, client: AsyncClient, auth_headers) -> None:
        entry = await _entry(client, auth_headers)
        created = (
            await client.post(f"/v1/entries/{entry['id']}/share", headers=auth_headers, json={})
        ).json()["data"]

        await client.get(f"/v1/shared/{created['token']}")
        await client.get(f"/v1/shared/{created['token']}")

        listing = await client.get("/v1/shares", headers=auth_headers)
        assert listing.json()["data"][0]["view_count"] == 2


class TestIntegrations:
    async def test_the_seven_providers_are_connectable(
        self, client: AsyncClient, auth_headers
    ) -> None:
        for provider in (
            "google_calendar",
            "outlook_calendar",
            "microsoft_todo",
            "slack",
            "teams",
            "notion",
            "obsidian",
        ):
            response = await client.post(
                "/v1/integrations",
                headers=auth_headers,
                json={"provider": provider, "access_token": "token-" + provider},
            )
            assert response.status_code == 201, f"{provider}: {response.text}"

        listing = await client.get("/v1/integrations", headers=auth_headers)
        assert len(listing.json()["data"]) == 7

    async def test_a_token_is_never_returned(self, client: AsyncClient, auth_headers) -> None:
        # It is encrypted before it touches a row, and no endpoint reads it
        # back — including this one.
        await client.post(
            "/v1/integrations",
            headers=auth_headers,
            json={"provider": "notion", "access_token": "secret-value-xyz"},
        )
        listing = await client.get("/v1/integrations", headers=auth_headers)
        assert "secret-value-xyz" not in listing.text

    async def test_two_way_is_refused_for_messaging(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # Slack has nothing to read. Accepting the setting would produce a
        # connection that silently syncs nothing.
        response = await client.post(
            "/v1/integrations",
            headers=auth_headers,
            json={"provider": "slack", "access_token": "t", "direction": "two_way"},
        )
        assert response.status_code == 422
        assert "sortante" in response.json()["detail"]

    async def test_obsidian_reports_that_it_is_client_side(
        self, client: AsyncClient, auth_headers
    ) -> None:
        created = (
            await client.post(
                "/v1/integrations",
                headers=auth_headers,
                json={"provider": "obsidian", "access_token": "none"},
            )
        ).json()["data"]

        assert created["server_side"] is False

        # And syncing says so rather than spinning forever.
        response = await client.post(f"/v1/integrations/{created['id']}/sync", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["failed"] is True
        assert "client" in response.json()["data"]["reason"]

    async def test_reconnecting_replaces_rather_than_duplicates(
        self, client: AsyncClient, auth_headers
    ) -> None:
        for token in ("first", "second"):
            await client.post(
                "/v1/integrations",
                headers=auth_headers,
                json={"provider": "notion", "access_token": token},
            )

        listing = await client.get("/v1/integrations", headers=auth_headers)
        notion = [row for row in listing.json()["data"] if row["provider"] == "notion"]
        assert len(notion) == 1

    async def test_disconnecting_clears_the_credentials(
        self, client: AsyncClient, auth_headers
    ) -> None:
        created = (
            await client.post(
                "/v1/integrations",
                headers=auth_headers,
                json={"provider": "notion", "access_token": "t"},
            )
        ).json()["data"]

        assert (
            await client.delete(f"/v1/integrations/{created['id']}", headers=auth_headers)
        ).status_code == 204

        listing = await client.get("/v1/integrations", headers=auth_headers)
        row = next(r for r in listing.json()["data"] if r["id"] == created["id"])
        assert row["status"] == "revoked"

    async def test_conflicts_start_empty(self, client: AsyncClient, auth_headers) -> None:
        response = await client.get("/v1/integrations/conflicts", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []


class TestAdmin:
    async def test_the_overview_counts_what_exists(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers)
        await _workspace(client, auth_headers, name="Espace")

        response = await client.get("/v1/admin/overview", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["members"] == 1
        assert data["workspaces"] == 1
        assert data["entries"] >= 1

    async def test_the_audit_window_is_bounded(self, client: AsyncClient, auth_headers) -> None:
        # Unbounded, the query scans every partition ever created.
        response = await client.get("/v1/admin/audit", headers=auth_headers)
        assert response.status_code == 200

    async def test_usage_is_reported_per_day(self, client: AsyncClient, auth_headers) -> None:
        await _entry(client, auth_headers)
        response = await client.get("/v1/admin/usage?days=7", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]

    async def test_health_reports_the_partition_gap(
        self, client: AsyncClient, auth_headers
    ) -> None:
        # The only place a missing audit partition is visible *before* it makes
        # every insert fail.
        response = await client.get("/v1/admin/health", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["audit_partitions"] > 0
        assert data["audit_partition_gap"] is False
