"""Le flux OAuth : ce qui se décide sans réseau, et ce qui se dit au fil.

Les cas épinglés ici sont ceux qui, tous, produisent la même panne vue de
l'utilisateur — « la synchronisation s'est arrêtée » — et des causes
complètement différentes. Ils sont donc écrits une fois, avec leur raison.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from app.config import Settings
from app.domain.oauth import (
    PROVIDERS,
    OAuthError,
    TokenGrant,
    expiry_from,
    make_pkce_pair,
    needs_refresh,
    provider_config,
    supports_oauth,
)
from app.domain.sync import Provider
from app.infra.crypto import KeyRing, generate_key
from app.infra.oauth import (
    OAuthClient,
    OAuthCredentials,
    credentials_for,
    decode_state,
    encode_state,
    redirect_uri_for,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
CREDENTIALS = OAuthCredentials(client_id="client-abc", client_secret="secret-xyz")


@pytest.fixture
def ring() -> KeyRing:
    return KeyRing.from_settings(f"k1:{generate_key()}")


def _client(provider: Provider = Provider.GOOGLE_CALENDAR) -> OAuthClient:
    return OAuthClient(
        provider_config(provider),
        CREDENTIALS,
        redirect_uri="https://app.mindflow.ai/integrations/google_calendar/callback",
    )


# -- Ce que chaque fournisseur exige ----------------------------------------- #


def test_google_asks_for_a_refresh_token_explicitly() -> None:
    """Le piège le plus cher du flux.

    Sans `access_type=offline` et `prompt=consent`, Google renvoie un jeton
    d'accès d'une heure et rien pour le renouveler — soit exactement le défaut
    que ce flux existe pour supprimer. Et comme la première autorisation d'un
    compte neuf en renvoie un malgré tout, l'oubli ne se voit qu'au second
    essai, des jours plus tard.
    """
    config = provider_config(Provider.GOOGLE_CALENDAR)
    assert config.extra_authorize_params["access_type"] == "offline"
    assert config.extra_authorize_params["prompt"] == "consent"


def test_microsoft_asks_for_offline_access_in_its_scopes() -> None:
    # Chez Microsoft, ce n'est pas un paramètre mais une portée. Même
    # conséquence en cas d'oubli.
    for provider in (Provider.OUTLOOK_CALENDAR, Provider.MICROSOFT_TODO):
        assert "offline_access" in provider_config(provider).scopes


def test_the_google_scope_is_events_not_the_whole_calendar() -> None:
    # `calendar` permettrait de supprimer des agendas entiers. Le moindre
    # privilège se décide ici, une fois, pas à la revue de sécurité.
    scopes = provider_config(Provider.GOOGLE_CALENDAR).scopes
    assert scopes == ("https://www.googleapis.com/auth/calendar.events",)


@pytest.mark.parametrize(
    "provider", [Provider.SLACK, Provider.TEAMS, Provider.NOTION, Provider.OBSIDIAN]
)
def test_providers_without_expiring_secrets_stay_out_of_the_flow(provider: Provider) -> None:
    """Slack, Teams, Notion et Obsidian n'ont rien à renouveler.

    URL de webhook entrant, jeton d'intégration interne, dossier local : rien
    n'expire. Les faire passer par OAuth ajouterait une cérémonie sans rien
    résoudre, et masquerait qu'ils fonctionnent déjà.
    """
    assert not supports_oauth(provider)
    with pytest.raises(OAuthError):
        provider_config(provider)


def test_every_oauth_provider_is_reachable_over_https() -> None:
    for config in PROVIDERS.values():
        assert config.authorize_url.startswith("https://")
        assert config.exchange_url.startswith("https://")


# -- PKCE --------------------------------------------------------------------- #


def test_the_pkce_challenge_is_the_sha256_of_the_verifier() -> None:
    # RFC 7636 §4.2 : base64url **sans remplissage**. Un `=` de trop et le
    # fournisseur répond `invalid_grant`, ce qui envoie chercher du côté du
    # code d'autorisation — au mauvais endroit.
    verifier, challenge = make_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()
    assert challenge == expected.rstrip("=")
    assert "=" not in challenge


def test_two_authorisations_never_share_a_verifier() -> None:
    assert make_pkce_pair()[0] != make_pkce_pair()[0]


# -- Le `state` --------------------------------------------------------------- #


def test_the_state_survives_a_round_trip(ring: KeyRing) -> None:
    account, user = uuid.uuid4(), uuid.uuid4()
    state = encode_state(
        ring=ring,
        account_id=account,
        user_id=user,
        provider=Provider.GOOGLE_CALENDAR,
        verifier="v" * 40,
        issued_at=NOW,
    )
    payload = decode_state(state, ring=ring, now=NOW + timedelta(minutes=1))

    assert payload.account_id == account
    assert payload.user_id == user
    assert payload.provider is Provider.GOOGLE_CALENDAR
    assert payload.verifier == "v" * 40


def test_the_verifier_is_not_readable_from_the_state(ring: KeyRing) -> None:
    """Chiffré, pas signé — et c'est tout l'intérêt.

    Le vérificateur PKCE traverse le navigateur dans le `state`. Signé, il y
    serait lisible, et PKCE ne protégerait plus de rien : quiconque intercepte
    le code intercepterait aussi de quoi l'échanger.
    """
    state = encode_state(
        ring=ring,
        account_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Provider.GOOGLE_CALENDAR,
        verifier="le-secret-a-ne-pas-montrer",
        issued_at=NOW,
    )
    assert "le-secret-a-ne-pas-montrer" not in state
    assert "google_calendar" not in state


def test_a_tampered_state_is_rejected(ring: KeyRing) -> None:
    state = encode_state(
        ring=ring,
        account_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Provider.GOOGLE_CALENDAR,
        verifier="v" * 40,
        issued_at=NOW,
    )
    broken = state[:-4] + ("AAAA" if not state.endswith("AAAA") else "BBBB")

    with pytest.raises(OAuthError) as error:
        decode_state(broken, ring=ring, now=NOW)
    assert error.value.terminal


def test_a_state_from_another_deployment_is_rejected(ring: KeyRing) -> None:
    # Le trousseau est la frontière : un `state` fabriqué ailleurs ne se
    # déchiffre pas ici, quelle que soit sa forme.
    other = KeyRing.from_settings(f"k1:{generate_key()}")
    state = encode_state(
        ring=other,
        account_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Provider.GOOGLE_CALENDAR,
        verifier="v" * 40,
        issued_at=NOW,
    )
    with pytest.raises(OAuthError):
        decode_state(state, ring=ring, now=NOW)


def test_a_state_expires(ring: KeyRing) -> None:
    # Un quart d'heure : le temps d'un écran de consentement. Au-delà, un
    # `state` qui traîne dans un historique devient une pièce rejouable.
    state = encode_state(
        ring=ring,
        account_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Provider.GOOGLE_CALENDAR,
        verifier="v" * 40,
        issued_at=NOW,
    )
    with pytest.raises(OAuthError, match="expirée"):
        decode_state(state, ring=ring, now=NOW + timedelta(minutes=16))


# -- L'adresse de consentement ------------------------------------------------ #


def test_the_authorisation_url_carries_everything_the_provider_needs() -> None:
    url = _client().authorisation_url(state="ST", challenge="CH")
    query = parse_qs(urlparse(url).query)

    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["CH"]
    assert query["state"] == ["ST"]
    assert query["access_type"] == ["offline"]
    assert query["redirect_uri"] == [
        "https://app.mindflow.ai/integrations/google_calendar/callback"
    ]
    # Le secret client n'a rien à faire dans une adresse que le navigateur voit.
    assert "client_secret" not in query


def test_the_redirect_uri_comes_from_one_place() -> None:
    """Dérivée, jamais configurée deux fois.

    Elle doit être identique à l'octet près entre l'autorisation, l'échange et
    la déclaration chez le fournisseur — sinon `redirect_uri_mismatch`, l'erreur
    la plus fréquente d'un premier branchement.
    """
    settings = Settings(env="local", public_base_url="https://app.mindflow.ai/")
    assert (
        redirect_uri_for(Provider.GOOGLE_CALENDAR, settings)
        == "https://app.mindflow.ai/integrations/google_calendar/callback"
    )


def test_an_unconfigured_provider_names_the_variable_to_fill() -> None:
    with pytest.raises(OAuthError, match="MINDFLOW_GOOGLE_CLIENT_ID"):
        credentials_for(Provider.GOOGLE_CALENDAR, Settings(env="local"))


# -- L'échange ---------------------------------------------------------------- #


@respx.mock
async def test_the_code_is_exchanged_for_a_grant() -> None:
    route = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3599,
                "scope": "https://www.googleapis.com/auth/calendar.events",
            },
        )
    )

    grant = await _client().exchange_code(code="the-code", verifier="the-verifier")

    assert grant.access_token == "at-1"
    assert grant.refresh_token == "rt-1"
    assert grant.expires_at is not None
    sent = dict(parse_qs(route.calls.last.request.content.decode()))
    assert sent["grant_type"] == ["authorization_code"]
    # Le vérificateur PKCE : sans lui, l'échange échoue, et c'est voulu.
    assert sent["code_verifier"] == ["the-verifier"]
    assert sent["client_secret"] == ["secret-xyz"]


@respx.mock
async def test_a_refresh_without_a_new_refresh_token_keeps_the_old_one() -> None:
    """Le cas Google, et le plus insidieux.

    La réponse est un succès. Elle ne contient pas de `refresh_token`. Écraser
    avec `None` casse la connexion au renouvellement *suivant* — une heure plus
    tard, sans rapport visible avec ce qui l'a causé.
    """
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "at-2", "expires_in": 3599})
    )

    grant = (await _client().refresh(refresh_token="rt-original")).merged_with("rt-original")

    assert grant.access_token == "at-2"
    assert grant.refresh_token == "rt-original"


@respx.mock
async def test_a_rotated_refresh_token_replaces_the_old_one() -> None:
    # Le cas Microsoft. Garder l'ancien ici serait l'erreur symétrique.
    respx.post(PROVIDERS[Provider.OUTLOOK_CALENDAR].exchange_url).mock(
        return_value=httpx.Response(
            200, json={"access_token": "at-3", "refresh_token": "rt-new", "expires_in": 3599}
        )
    )

    client = _client(Provider.OUTLOOK_CALENDAR)
    grant = (await client.refresh(refresh_token="rt-old")).merged_with("rt-old")

    assert grant.refresh_token == "rt-new"


@respx.mock
async def test_a_revoked_grant_is_terminal() -> None:
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "Token has been expired"}
        )
    )

    with pytest.raises(OAuthError) as error:
        await _client().refresh(refresh_token="rt-revoked")
    assert error.value.terminal


@respx.mock
async def test_a_provider_outage_is_not_terminal() -> None:
    # Un 503 est passager. Le marquer terminal demanderait à l'utilisateur de
    # reconnecter un service qui allait revenir tout seul.
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(503, text="upstream unavailable")
    )

    with pytest.raises(OAuthError) as error:
        await _client().refresh(refresh_token="rt-1")
    assert not error.value.terminal


@respx.mock
async def test_an_unreachable_provider_is_not_terminal() -> None:
    respx.post("https://oauth2.googleapis.com/token").mock(side_effect=httpx.ConnectError("nope"))

    with pytest.raises(OAuthError) as error:
        await _client().exchange_code(code="c", verifier="v")
    assert not error.value.terminal


@respx.mock
async def test_a_success_without_an_access_token_is_terminal() -> None:
    # Un 200 vide est un contrat rompu, pas une panne passagère : réessayer
    # produirait exactement le même vide, indéfiniment.
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"token_type": "Bearer"})
    )

    with pytest.raises(OAuthError) as error:
        await _client().exchange_code(code="c", verifier="v")
    assert error.value.terminal


@respx.mock
async def test_the_error_body_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Une réponse d'erreur peut contenir la requête qui l'a produite.

    Donc le secret client. Le journal porte le code d'erreur et le statut, pas
    le corps.
    """
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            400, json={"error": "invalid_client", "client_secret": "secret-xyz"}
        )
    )

    with caplog.at_level("WARNING"), pytest.raises(OAuthError):
        await _client().exchange_code(code="c", verifier="v")

    assert "secret-xyz" not in caplog.text


# -- Quand renouveler --------------------------------------------------------- #


def test_a_token_is_refreshed_before_it_expires() -> None:
    # Attendre le 401 coûte une passe de synchronisation entière, et à cinq
    # minutes de cadence cela se voit.
    assert needs_refresh(NOW + timedelta(seconds=30), now=NOW)
    assert not needs_refresh(NOW + timedelta(minutes=30), now=NOW)


def test_an_already_expired_token_needs_refreshing() -> None:
    assert needs_refresh(NOW - timedelta(hours=2), now=NOW)


def test_a_token_without_a_known_expiry_is_left_alone() -> None:
    # On ne renouvelle pas un jeton dont rien ne dit qu'il est fatigué ; le 401
    # reste le filet.
    assert not needs_refresh(None, now=NOW)


def test_a_naive_expiry_is_read_as_utc() -> None:
    """Les colonnes sans fuseau remontent naïves.

    Les traiter comme locales décalerait l'expiration de plusieurs heures — dans
    un sens ou dans l'autre selon le fuseau du serveur, ce qui est la pire forme
    d'un bogue : dépendant de l'endroit où il tourne.
    """
    assert needs_refresh(NOW.replace(tzinfo=None) - timedelta(hours=1), now=NOW)


@pytest.mark.parametrize("value", [None, "", "bientôt", 0, -10, True, {"a": 1}])
def test_an_unusable_expires_in_yields_no_expiry(value: object) -> None:
    assert expiry_from(value, now=NOW) is None


def test_expires_in_accepts_the_string_some_providers_send() -> None:
    assert expiry_from("3600", now=NOW) == NOW + timedelta(seconds=3600)


def test_nothing_to_keep_stays_nothing() -> None:
    # Une connexion sans jeton de rafraîchissement n'en gagne pas un par
    # accident : elle vivra une heure et demandera une reconnexion, ce qui est
    # au moins un comportement lisible.
    grant = TokenGrant(access_token="a", refresh_token=None, expires_at=None)
    assert grant.merged_with(None).refresh_token is None
