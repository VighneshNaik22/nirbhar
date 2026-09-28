from fastapi.testclient import TestClient

from app.knowledge import retrieve_sop_chunks
from app.main import app

client = TestClient(app)


def test_activate_pack_and_retrieve_relevant_sop():
    activate = client.post("/api/pack/activate", json={"pack": "campus"})
    assert activate.status_code == 200, activate.text
    body = activate.json()
    assert body["pack"] == "campus"

    result = client.post(
        "/api/knowledge/retrieve",
        json={"query": "fire alarm evacuation and smoke detection", "top_k": 3},
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["results"]
    assert any("Alarm & Evacuation" in chunk["section"] or "Detection & Verification" in chunk["section"] for chunk in payload["results"])


def test_no_matching_sop_returns_review_required():
    result = retrieve_sop_chunks("quantum teleportation for alien contact", top_k=3, threshold=0.6)
    assert result[0]["text"] == "Review Required - no matching SOP found"
