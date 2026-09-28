from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_heatmap_endpoint_returns_zone_risk_levels_and_banner():
    response = client.get("/api/heatmap")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["label"] == "SYNTHETIC - illustrative, not predictive"
    assert payload["zones"]
    assert any("risk" in zone for zone in payload["zones"][0])
