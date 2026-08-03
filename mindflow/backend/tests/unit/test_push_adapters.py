"""Push adapters: payload shape and the error mapping that matters.

The interesting behaviour here is not "did it POST" — it is which failures
retire a token permanently and which ones do not. Retiring a token on a
temporary fault silently unsubscribes a user who did nothing wrong; never
retiring one means the dispatcher repeats a doomed request every minute for
ever.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.domain.enums import PushProvider
from app.domain.ports import PushMessage
from app.infra.push.factory import build_push_sender, reset_senders
from app.infra.push.fake import FakePushSender
from app.infra.push.fcm import FcmPushSender, _payload
from app.infra.push.wns import WnsPushSender, _toast_xml

MESSAGE = PushMessage(
    title="Rappeler le DAF",
    body="C'est bientôt.",
    data={"type": "reminder", "entry_id": "e1"},
    collapse_key="entry-e1",
)


def _service_account_json() -> str:
    """A real RSA key, generated once.

    A placeholder string will not do: the adapter signs a JWT with this key, so
    a fake one fails at the signing step and every test below would exercise the
    auth-failure path instead of the path it names.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "client_email": "svc@example.iam.gserviceaccount.com",
            "private_key": pem,
            "project_id": "mindflow-test",
        }
    )


CREDENTIALS = _service_account_json()


@pytest.fixture(autouse=True)
def _clean_senders() -> None:
    reset_senders()


class TestFactory:
    def test_local_and_none_have_no_server_side_sender(self) -> None:
        """A locally scheduled Windows toast is the client's job (ADR-040), and
        a device that never registered a token has nowhere to send to."""
        settings = Settings(env="local")
        assert build_push_sender(settings, PushProvider.LOCAL) is None
        assert build_push_sender(settings, PushProvider.NONE) is None

    def test_the_fake_backend_wins_over_the_provider(self) -> None:
        settings = Settings(env="local", push_backend="fake")
        sender = build_push_sender(settings, PushProvider.FCM)
        assert isinstance(sender, FakePushSender)

    def test_senders_are_cached(self) -> None:
        """Rebuilding per batch would refetch a Google access token every
        minute."""
        settings = Settings(env="local", push_backend="fake")
        assert build_push_sender(settings, PushProvider.FCM) is build_push_sender(
            settings, PushProvider.FCM
        )


class TestFcmPayload:
    def test_carries_the_routing_data_as_strings(self) -> None:
        payload = _payload("token-1", MESSAGE)
        assert payload["token"] == "token-1"
        assert payload["data"] == {"type": "reminder", "entry_id": "e1"}
        assert payload["notification"]["title"] == "Rappeler le DAF"

    def test_sets_the_collapse_key_on_both_platforms(self) -> None:
        """A second reminder about one task replaces the first on the lock
        screen instead of stacking. Stacking is the main reason people disable
        an app's notifications outright."""
        payload = _payload("token-1", MESSAGE)
        assert payload["android"]["collapse_key"] == "entry-e1"
        assert payload["apns"]["headers"]["apns-collapse-id"] == "entry-e1"

    def test_omits_the_collapse_key_when_there_is_none(self) -> None:
        payload = _payload("t", PushMessage(title="a", body="b", data={}))
        assert "collapse_key" not in payload["android"]
        assert "headers" not in payload["apns"]


class TestFcmErrors:
    async def test_unregistered_retires_only_that_token(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
            body = request.content.decode()
            if "dead" in body:
                return httpx.Response(
                    404,
                    json={"error": {"details": [{"errorCode": "UNREGISTERED"}]}},
                )
            return httpx.Response(200, json={"name": "ok"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            sender = FcmPushSender(
                Settings(env="local", fcm_service_account_json=CREDENTIALS), client=client
            )
            result = await sender.send(["live", "dead"], MESSAGE)

        assert result.delivered == 1
        assert result.invalid_tokens == ("dead",)
        assert result.retryable_tokens == ()

    async def test_a_server_error_is_retryable_not_permanent(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
            return httpx.Response(503, json={"error": {}})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            sender = FcmPushSender(
                Settings(env="local", fcm_service_account_json=CREDENTIALS), client=client
            )
            result = await sender.send(["a"], MESSAGE)

        assert result.invalid_tokens == ()
        assert result.retryable_tokens == ("a",)

    async def test_an_auth_failure_marks_everything_retryable(self) -> None:
        """The failure is ours, not the devices'."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            sender = FcmPushSender(
                Settings(env="local", fcm_service_account_json=CREDENTIALS), client=client
            )
            result = await sender.send(["a", "b"], MESSAGE)

        assert result.error == "fcm_auth_failed"
        assert set(result.retryable_tokens) == {"a", "b"}

    async def test_bad_credentials_disable_push_without_crashing(self) -> None:
        """A malformed key must not stop the API from serving requests that have
        nothing to do with notifications."""
        sender = FcmPushSender(Settings(env="local", fcm_service_account_json="{oops"))
        result = await sender.send(["a"], MESSAGE)
        assert result.error == "fcm_not_configured"


class TestWns:
    def test_escapes_xml_in_user_content(self) -> None:
        """A task titled `Rappeler <DAF> & co` would otherwise produce a
        malformed document, and WNS answers that with a 400 indistinguishable
        from a configuration problem."""
        xml = _toast_xml(
            PushMessage(title="Rappeler <DAF> & co", body='dit "demain"', data={"a": "1&2"})
        ).decode()
        assert "<DAF>" not in xml
        assert "&lt;DAF&gt; &amp; co" in xml
        assert "&quot;demain&quot;" in xml or "demain" in xml

    async def test_410_retires_the_channel(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if "accesstoken" in str(request.url):
                return httpx.Response(200, json={"access_token": "at", "expires_in": 86400})
            return httpx.Response(410)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            sender = WnsPushSender(
                Settings(env="local", wns_client_id="id", wns_client_secret="secret"),
                client=client,
            )
            result = await sender.send(["https://db5.notify.windows.com/x"], MESSAGE)

        assert result.invalid_tokens == ("https://db5.notify.windows.com/x",)

    async def test_unconfigured_reports_rather_than_raises(self) -> None:
        sender = WnsPushSender(Settings(env="local"))
        result = await sender.send(["https://db5.notify.windows.com/x"], MESSAGE)
        assert result.error == "wns_not_configured"


class TestFake:
    async def test_records_what_it_was_asked_to_send(self) -> None:
        """The interesting bugs here are wrong titles and missing routing data,
        not missing calls — so the fake records content, not just counts."""
        sender = FakePushSender()
        await sender.send(["a", "b"], MESSAGE)
        assert sender.sent[0].message.title == "Rappeler le DAF"
        assert sender.sent[0].message.data["entry_id"] == "e1"

    async def test_can_pretend_a_token_is_dead(self) -> None:
        sender = FakePushSender(dead_tokens={"b"})
        result = await sender.send(["a", "b"], MESSAGE)
        assert result.delivered == 1
        assert result.invalid_tokens == ("b",)
