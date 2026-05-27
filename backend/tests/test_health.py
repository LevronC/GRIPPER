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


def test_institutions_public_list(client: TestClient):
    response = client.get("/institutions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "name" in data[0]
