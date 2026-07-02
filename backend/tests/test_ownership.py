import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "demo_users", "demo:demo,alice:alice")
    monkeypatch.setattr(settings, "jwt_secret", "test-secret")
    init_db()
    return TestClient(app)


def test_login_invalid(client):
    res = client.post("/auth/login", json={"username": "demo", "password": "wrong"})
    assert res.status_code == 401


def test_users_only_see_own_runs(client):
    demo_headers = {
        "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'demo', 'password': 'demo'}).json()['access_token']}"
    }
    run_id = client.post("/runs", json={"preset": "linear"}, headers=demo_headers).json()["run_id"]

    detail = client.get(f"/runs/{run_id}", headers=demo_headers).json()
    assert detail["submitted_by"] == "demo"

    alice_headers = {
        "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'alice'}).json()['access_token']}"
    }
    assert client.get(f"/runs/{run_id}", headers=alice_headers).status_code == 404
    assert client.get("/runs", headers=alice_headers).json() == []


def test_runs_submitted_metric_has_user_label(client):
    demo_headers = {
        "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'demo', 'password': 'demo'}).json()['access_token']}"
    }
    client.post("/runs", json={"preset": "linear"}, headers=demo_headers)
    metrics = client.get("/metrics").text
    assert 'workflow_runs_submitted_total{user="demo"}' in metrics


def test_submit_requires_login(client):
    res = client.post("/runs", json={"preset": "linear"})
    assert res.status_code == 401
