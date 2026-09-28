from app.config import settings
from app.correlate import correlate_evidence
from app.db import init_db
from app.intake import normalize_report, normalize_sensor
from app.reason import build_recommendation, build_what_would_change_my_mind
from app.schema import ReportInput, SensorInput


def _setup(tmp_path, monkeypatch):
    db_path = tmp_path / "nirbhar_phase3.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    init_db(str(db_path))


def test_correlate_evidence_into_confirmed_incident(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    normalize_report(ReportInput(
        zone="Hostel-A-Room-204",
        reporter_role="student",
        description="Strong smoke smell in the room.",
        severity_hint=4,
        source_type="student_report",
        timestamp="2026-01-01T12:00:00Z",
    ))
    normalize_sensor(SensorInput(
        zone="Hostel-A-Room-204",
        sensor_type="smoke",
        value=0.8,
        timestamp="2026-01-01T12:03:00Z",
    ))

    incident = correlate_evidence()[0]
    assert incident["confidence"] == "Confirmed"
    assert "smoke" in incident["reason"].lower() or "report" in incident["reason"].lower()


def test_reasoning_builds_cited_recommendations_and_would_change_my_mind(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    chunks = [
        {
            "file": "fire_safety.md",
            "section": "Alarm & Evacuation",
            "text": "Raise the nearest alarm and initiate evacuation if smoke or fire is confirmed.",
        },
        {
            "file": "fire_safety.md",
            "section": "Detection & Verification",
            "text": "Verify the source of the alarm before taking action.",
        },
    ]

    recommendation = build_recommendation(
        zone="Hostel-A-Room-204",
        category="fire_smoke",
        retrieved_chunks=chunks,
    )
    assert recommendation["status"] == "ok"
    assert recommendation["steps"]
    assert all("[SOP:" in step for step in recommendation["steps"])

    what_if = build_what_would_change_my_mind("fire_smoke")
    assert what_if["escalate_if"]
    assert what_if["de_escalate_if"]
    assert what_if["missing_evidence"]


def test_no_sop_found_returns_exact_message(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    recommendation = build_recommendation(
        zone="Hostel-Z-Room-999",
        category="other",
        retrieved_chunks=[],
    )
    assert recommendation["status"] == "review_required"
    assert recommendation["message"] == "Review Required - no matching SOP found"
