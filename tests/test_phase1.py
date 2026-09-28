import sqlite3

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_connection, init_db
from app.main import app


client = TestClient(app)


def _prepare_db(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase1.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))
    return str(db_path)


def test_reports_and_sensor_intake(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    report_response = client.post(
        "/api/reports",
        json={
            "zone": "Hostel-A-Room-204",
            "reporter_role": "student",
            "description": "There is a strong smoke smell near the room.",
            "severity_hint": 4,
            "source_type": "student_report",
        },
    )
    assert report_response.status_code == 200, report_response.text
    report_body = report_response.json()
    assert report_body["success"] is True
    assert report_body["evidence"]["source_type"] == "student_report"
    assert report_body["evidence"]["category"] == "fire_smoke"

    sensor_response = client.post(
        "/api/sensors",
        json={
            "zone": "Hostel-A-Room-204",
            "sensor_type": "smoke",
            "value": 0.8,
            "timestamp": "2026-01-01T12:00:00Z",
        },
    )
    assert sensor_response.status_code == 200, sensor_response.text
    sensor_body = sensor_response.json()
    assert sensor_body["success"] is True
    assert sensor_body["evidence"]["sensor_type"] == "smoke"

    with get_connection() as conn:
        evidence_count = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    assert evidence_count >= 2


def test_audit_chain_verification_and_tamper_detection(tmp_path, monkeypatch):
    db_path = _prepare_db(tmp_path, monkeypatch)

    client.post(
        "/api/reports",
        json={
            "zone": "Hostel-B-Room-110",
            "reporter_role": "guard",
            "description": "Guard saw smoke near the corridor.",
            "severity_hint": 3,
            "source_type": "guard_report",
        },
    )

    verify_response = client.get("/api/audit/verify")
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "intact"

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
        conn.execute("UPDATE audit_log SET payload_json = 'tampered' WHERE id = 1")
        conn.commit()

    tampered_response = client.get("/api/audit/verify")
    assert tampered_response.status_code == 200
    assert tampered_response.json()["status"] == "tampered"

    audit_response = client.get("/api/audit")
    assert audit_response.status_code == 200
    entries = audit_response.json()
    assert len(entries) >= 2
