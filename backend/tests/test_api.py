import os

import pytest
from fastapi.testclient import TestClient

os.environ["AUTH_DISABLED"] = "true"
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_workflow.db"
os.environ["OTEL_ENABLED"] = "false"

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    if os.path.exists("/tmp/test_workflow.db"):
        os.remove("/tmp/test_workflow.db")
    init_db()
    return TestClient(app)


def test_submit_and_get_run(client):
    res = client.post("/runs", json={"preset": "linear"})
    assert res.status_code == 202
    run_id = res.json()["run_id"]

    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] in ("pending", "running", "completed")
    assert len(detail.json()["steps"]) == 4


def test_list_presets(client):
    res = client.get("/presets")
    assert res.status_code == 200
    assert any(p["id"] == "fanout" for p in res.json())
