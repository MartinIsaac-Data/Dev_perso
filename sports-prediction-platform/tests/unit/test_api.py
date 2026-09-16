from __future__ import annotations

from fastapi.testclient import TestClient
from spp.api.main import create_app
from spp.common.errors import InsufficientDataError


def test_health_lists_registered_sports() -> None:
    client = TestClient(create_app())
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert set(body["sports"]) == {"basketball", "football", "tennis"}


def test_model_health_declares_signals_suspended_without_a_model() -> None:
    client = TestClient(create_app())
    body = client.get("/api/v1/health/models").json()
    assert body["signals_suspended"] is True
    assert body["champion"] is None


def test_root_carries_the_disclaimer() -> None:
    client = TestClient(create_app())
    body = client.get("/api/v1").json()
    assert "incertitude" in body["disclaimer"]


def test_insufficient_data_maps_to_422_problem_json() -> None:
    app = create_app()

    @app.get("/api/v1/_boom")
    def _boom() -> None:
        raise InsufficientDataError("Aucune cote disponible.", missing=["odds"], data_quality=0.31)

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/_boom")
    assert r.status_code == 422
    body = r.json()
    assert body["missing"] == ["odds"]
    assert body["data_quality"] == 0.31


def test_openapi_is_generated() -> None:
    client = TestClient(create_app())
    assert client.get("/openapi.json").status_code == 200
