"""Health and public endpoint tests."""

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "Gripper" in response.json()["message"]
