"""Le contrôle d'accès inter-origines, vu comme un navigateur le voit.

Ce fichier existe parce que l'API n'a eu aucun CORS pendant quatre phases et que
rien ne l'a signalé. C'est logique : les tests HTTP parlent à l'application en
ASGI, sans origine ; `flutter test` ne fait pas de requête réseau ; et le test
de fumée web n'appelle jamais l'API. Le seul endroit d'où le défaut est visible
est un navigateur servi sur une autre origine — exactement la configuration dans
laquelle un utilisateur découvre le produit.

Ce que le navigateur exige, et qui est vérifié ici :

* le pré-vol `OPTIONS` doit répondre sans authentification — il part *avant* la
  requête, sans en-tête `Authorization` ;
* la réponse doit renvoyer l'origine ;
* `X-Request-Id` doit être exposé, sinon le JavaScript ne peut pas le lire et un
  incident client devient impossible à relier à un journal serveur.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

LOCAL = "http://localhost:8080"


def _client(settings: Settings) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app(settings)), base_url="http://api")


async def test_a_local_page_may_call_the_api() -> None:
    async with _client(Settings(env="local")) as http:
        response = await http.get("/health", headers={"Origin": LOCAL})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL


async def test_the_preflight_passes_without_a_token() -> None:
    # Le pré-vol part sans `Authorization` : s'il exigeait un jeton, aucune
    # requête authentifiée ne partirait jamais, ce qui est le cas dégénéré le
    # plus déroutant du CORS.
    async with _client(Settings(env="local")) as http:
        response = await http.options(
            "/v1/captures",
            headers={
                "Origin": LOCAL,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test_the_request_id_is_readable_by_the_client() -> None:
    async with _client(Settings(env="local")) as http:
        response = await http.get("/health", headers={"Origin": LOCAL})

    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


async def test_an_unknown_origin_gets_nothing() -> None:
    async with _client(Settings(env="local")) as http:
        response = await http.get("/health", headers={"Origin": "http://exemple.test"})

    # La requête aboutit — c'est le navigateur, pas le serveur, qui refuse la
    # réponse — mais l'en-tête qui l'autoriserait est absent.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", [LOCAL, "https://app.mindflow.ai"])
async def test_production_only_answers_the_origins_it_was_given(origin: str) -> None:
    settings = Settings(
        env="prod",
        supabase_jwks_url="https://x.supabase.co/auth/v1/.well-known/jwks.json",
        stt_backend="faster_whisper",
        llm_backend="openai",
        openai_api_key="sk-test",
        push_backend="real",
        fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
        token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
        public_base_url="https://app.mindflow.ai",
        embedding_backend="openai",
        chat_backend="openai",
        cors_allow_origins="https://app.mindflow.ai",
    )
    async with _client(settings) as http:
        response = await http.get("/health", headers={"Origin": origin})

    allowed = response.headers.get("access-control-allow-origin")
    assert allowed == (origin if origin.startswith("https://app.") else None)


async def test_no_headers_at_all_when_nothing_is_configured() -> None:
    """Le cas du déploiement mono-origine.

    Le client web est servi par le même hôte que l'API : il n'y a pas de requête
    inter-origines, donc pas d'en-tête à émettre. Ne rien ouvrir par défaut est
    la bonne posture, et c'est ce que fait la production.
    """
    settings = Settings(
        env="staging",
        supabase_jwks_url="https://x.supabase.co/auth/v1/.well-known/jwks.json",
        stt_backend="faster_whisper",
        llm_backend="openai",
        openai_api_key="sk-test",
        push_backend="real",
        fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
        token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
        public_base_url="https://staging.mindflow.ai",
        embedding_backend="openai",
        chat_backend="openai",
    )
    async with _client(settings) as http:
        response = await http.get("/health", headers={"Origin": LOCAL})

    assert "access-control-allow-origin" not in response.headers
