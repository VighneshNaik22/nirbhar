from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.main import app

client = TestClient(app)


def _reset_db(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase4.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))


def test_approve_creates_simulated_ticket_and_reject_requires_reason(tmp_path, monkeypatch):
    _reset_db(tmp_path, monkeypatch)

    create_result = client.post(
        "/api/incidents/1/approve",
        json={"decision": "approve", "reason": "Officer confirmed smoke and ordered evacuation."},
    )
    assert create_result.status_code == 200, create_result.text
    body = create_result.json()
    assert body["status"] == "simulated - not dispatched"
    assert body["ticket_id"]

    reject_result = client.post(
        "/api/incidents/1/reject",
        json={"reason": ""},
    )
    assert reject_result.status_code == 422

    modify_result = client.post(
        "/api/incidents/1/modify",
        json={"reason": "Adjust response to include the warden."},
    )
    assert modify_result.status_code == 200
    assert modify_result.json()["status"] == "simulated - not dispatched"


def test_no_ticket_without_approval_record(tmp_path, monkeypatch):
    _reset_db(tmp_path, monkeypatch)
    response = client.get("/api/tickets")
    assert response.status_code == 200
    assert response.json() == []
