from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_permits_configured_frontend() -> None:
    settings = Settings(cors_origins=["https://web.example.test"])
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"Origin": "https://web.example.test"})
    assert response.headers["access-control-allow-origin"] == "https://web.example.test"


def test_cors_does_not_permit_unknown_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": "https://untrusted.example.test"})
    assert "access-control-allow-origin" not in response.headers
