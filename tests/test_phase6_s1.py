from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.main import app

client = TestClient(app)


def test_evidence_graph_endpoint_returns_nodes_and_edges(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase6_s1.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))

    response = client.get("/api/graph")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "nodes" in payload
    assert "edges" in payload
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
