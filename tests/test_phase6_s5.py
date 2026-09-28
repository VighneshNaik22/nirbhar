from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.demo import load_demo
from app.main import app

client = TestClient(app)


def test_memory_search_finds_prior_incidents_and_evidence(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase6_s5.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))
    load_demo()

    response = client.get("/api/memory/search", params={"query": "smoke"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["results"]
    assert any(item["zone"] == "Hostel-A-Room-204" for item in payload["results"])
