from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.demo import load_demo
from app.main import app

client = TestClient(app)


def test_role_default_and_warden_view_are_non_empty(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase6_s4.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))
    load_demo()

    all_response = client.get("/api/incidents")
    assert all_response.status_code == 200, all_response.text
    assert all_response.json()

    warden_response = client.get("/api/role-view/warden")
    assert warden_response.status_code == 200, warden_response.text
    payload = warden_response.json()
    assert payload["role"] == "warden"
    assert payload["incidents"]
    assert {item["zone"] for item in payload["incidents"]} <= {item["zone"] for item in all_response.json()}
