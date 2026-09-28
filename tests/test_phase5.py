from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.demo import load_demo, reset_demo
from app.main import app

client = TestClient(app)


def _reset(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase5.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))


def test_load_reset_demo_and_expected_incidents(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    load_demo()

    incidents = client.get("/api/incidents")
    assert incidents.status_code == 200, incidents.text
    payload = incidents.json()
    assert len(payload) >= 3
    labels = {item["zone"]: item["confidence"] for item in payload}
    assert labels.get("Hostel-A-Room-204") in {"Confirmed"}
    assert labels.get("Hostel-B-Room-110") in {"Sensor-only"}
    assert labels.get("Hostel-C-Room-305") in {"Normal/Below threshold"}

    logs = client.get("/api/audit")
    assert logs.status_code == 200
    assert len(logs.json()) >= 6

    reset_demo()
    assert client.get("/api/incidents").json() == []
