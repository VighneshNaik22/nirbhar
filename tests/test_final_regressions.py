from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import init_db
from app.demo import load_demo
from app.main import app

client = TestClient(app)


def _reset(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_final.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))
    load_demo()


def test_role_view_officer_sees_all_incidents(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    officer = client.get("/api/role-view/officer").json()
    assert officer["role"] == "officer"
    assert len(officer["incidents"]) == len(incidents)


def test_detail_endpoint_and_room_b_missing_evidence(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    room_a = next(item for item in incidents if item["zone"] == "Hostel-A-Room-204")
    room_b = next(item for item in incidents if item["zone"] == "Hostel-B-Room-110")

    detail_a = client.get(f"/api/incidents/{room_a['id']}")
    assert detail_a.status_code == 200, detail_a.text
    payload_a = detail_a.json()
    assert payload_a["recommendation"]["steps"]
    assert any("[SOP:" in step for step in payload_a["recommendation"]["steps"])

    detail_b = client.get(f"/api/incidents/{room_b['id']}")
    assert detail_b.status_code == 200, detail_b.text
    payload_b = detail_b.json()
    assert payload_b["recommendation"]["missing_evidence"]


def test_approve_reason_optional_and_modify_reject_require_reason(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    room_a = next(item for item in incidents if item["zone"] == "Hostel-A-Room-204")

    approve = client.post(f"/api/incidents/{room_a['id']}/approve", json={})
    assert approve.status_code == 200, approve.text
    assert approve.json()["ticket_id"]

    modify = client.post(f"/api/incidents/{room_a['id']}/modify", json={})
    assert modify.status_code == 422, modify.text

    reject = client.post(f"/api/incidents/{room_a['id']}/reject", json={"reason": ""})
    assert reject.status_code == 422, reject.text


def test_ragging_is_categorized_and_cited(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    room_d = next(item for item in incidents if item["zone"] == "Hostel-D-Common-Area")
    detail = client.get(f"/api/incidents/{room_d['id']}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["incident"]["category"] == "ragging"
    assert any("anti_ragging" in step for step in payload["recommendation"]["steps"])


def test_room_c_no_extra_normal_incident(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    room_c = [item for item in incidents if item["zone"] == "Hostel-C-Room-305"]
    assert len(room_c) == 1
    assert room_c[0]["confidence"] == "Normal/Below threshold"


def test_health_reports_llm_and_retriever_status(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    response = client.get("/api/health")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["llm_status"] in {"online", "offline - template mode"}
    assert payload["retriever"] in {"chroma", "bm25-fallback"}


def test_ticket_actions_use_saved_recommendation_steps(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    room_a = next(item for item in incidents if item["zone"] == "Hostel-A-Room-204")
    approve = client.post(f"/api/incidents/{room_a['id']}/approve", json={"reason": "Confirmed by two reports"})
    assert approve.status_code == 200, approve.text
    ticket = client.get("/api/tickets").json()[0]
    assert ticket["incident_id"] == room_a["id"]
    assert any("[SOP:" in action for action in ticket["actions"])


def test_demo_reset_clears_tickets_and_preserves_audit_chain(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    room_a = next(item for item in client.get("/api/incidents").json() if item["zone"] == "Hostel-A-Room-204")
    approved = client.post(f"/api/incidents/{room_a['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert client.get("/api/tickets").json()

    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200, reset.text
    assert client.get("/api/tickets").json() == []
    assert client.get("/api/incidents").json() == []
    assert client.get("/api/audit/verify").json()["status"] == "intact"
    assert any(event["event_type"] == "demo_reset" for event in client.get("/api/audit").json())


def test_demo_recommendations_and_tickets_are_category_scoped(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    incidents = client.get("/api/incidents").json()
    by_zone = {item["zone"]: item for item in incidents}

    room_a = client.get(f"/api/incidents/{by_zone['Hostel-A-Room-204']['id']}").json()
    room_d = client.get(f"/api/incidents/{by_zone['Hostel-D-Common-Area']['id']}").json()
    room_c = client.get(f"/api/incidents/{by_zone['Hostel-C-Room-305']['id']}").json()
    assert {chunk["file"] for chunk in room_a["recommendation"]["cited_chunks"]} == {"fire_safety.md"}
    assert {chunk["file"] for chunk in room_d["recommendation"]["cited_chunks"]} == {"anti_ragging.md"}
    assert room_c["recommendation"]["steps"] == []
    assert room_c["recommendation"]["message"] == "No action required - monitor"

    approved = client.post(f"/api/incidents/{by_zone['Hostel-A-Room-204']['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    ticket = client.get("/api/tickets").json()[0]
    assert ticket["actions"]
    assert all("fire_safety.md" in action for action in ticket["actions"])


def test_sensor_only_incident_recommends_verification_only(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    room_b = next(item for item in client.get("/api/incidents").json() if item["zone"] == "Hostel-B-Room-110")
    recommendation = client.get(f"/api/incidents/{room_b['id']}").json()["recommendation"]
    assert any("Detection & Verification" in step for step in recommendation["steps"])
    assert all("Alarm & Evacuation" not in step for step in recommendation["steps"])
    assert all("Isolation of Power" not in step for step in recommendation["steps"])


def test_demo_seed_timestamps_are_recent(tmp_path, monkeypatch):
    from app.db import get_connection

    _reset(tmp_path, monkeypatch)
    with get_connection() as conn:
        rows = conn.execute("SELECT timestamp FROM evidence").fetchall()
    timestamps = [datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) for row in rows]
    now = datetime.now(timezone.utc)
    assert timestamps
    assert all(timedelta(0) <= now - timestamp < timedelta(minutes=15) for timestamp in timestamps)
