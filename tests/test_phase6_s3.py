from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_factory_pack_activation_and_retrieval():
    activate = client.post("/api/pack/activate", json={"pack": "factory"})
    assert activate.status_code == 200, activate.text
    assert activate.json()["pack"] == "factory"

    result = client.post(
        "/api/knowledge/retrieve",
        json={"query": "worker without PPE near heat sensor spike", "top_k": 3, "pack": "factory"},
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["results"]
    assert any("PPE Requirements" in chunk["section"] or "Heat Stress Thresholds" in chunk["section"] for chunk in payload["results"])
