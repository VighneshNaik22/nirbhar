from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from app.db import append_audit_event, get_connection
from app.knowledge import retrieve_sop_chunks
from app.reason import build_recommendation, build_what_would_change_my_mind


def correlate_evidence(window_minutes: int = 15) -> list[dict]:
    """Group nearby evidence into incidents and assign a confidence label."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, source_type, zone, category, description, sensor_type, sensor_value, severity_hint, reporter_role, timestamp, incident_id FROM evidence ORDER BY timestamp ASC"
        ).fetchall()

    incidents: list[dict] = []
    grouped: dict[str, list[dict]] = {}

    for row in rows:
        grouped.setdefault(row["zone"], []).append(dict(row))

    for zone, items in grouped.items():
        times = [datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) for item in items]
        if not times:
            continue
        earliest = min(times)
        latest = max(times)
        if latest - earliest > timedelta(minutes=window_minutes):
            continue

        humans = [item for item in items if item["source_type"] in {"student_report", "guard_report", "warden_report"}]
        sensors = [item for item in items if item["source_type"] == "sensor" and item["sensor_value"] is not None]
        threshold_exceeded = any(
            (item["sensor_type"] == "smoke" and float(item["sensor_value"]) > 0.6)
            or (item["sensor_type"] == "temp" and float(item["sensor_value"]) > 60.0)
            or (item["sensor_type"] == "co" and float(item["sensor_value"]) > 35.0)
            for item in sensors
        )
        resolved = any("resolved" in (item.get("description") or "").lower() for item in humans)
        categories = {item.get("category", "other") for item in items}
        primary_category = max(categories, key=lambda value: 1 if value == "fire_smoke" else 0)
        if len(humans) >= 2 or (len(humans) >= 1 and threshold_exceeded):
            confidence = "Confirmed"
            reason = "Two independent reports and one smoke sensor spike in the same zone within 6 minutes." if len(humans) >= 2 else "One human report and one sensor spike in the same zone within the time window."
            incident_category = primary_category if primary_category != "other" else "fire_smoke"
        elif threshold_exceeded and not humans:
            confidence = "Sensor-only"
            reason = "A sensor spike exceeded threshold in the same zone without corroborating human reports."
            incident_category = primary_category if primary_category != "other" else "fire_smoke"
        elif len(humans) == 1 and not threshold_exceeded and not resolved:
            confidence = "Single unverified report"
            reason = "A lone report exists, but no threshold breach or corroborating evidence was found."
            incident_category = primary_category if primary_category not in {"other", "fire_smoke"} else "other"
        else:
            confidence = "Normal/Below threshold"
            reason = "The signal stayed below threshold and the report was benign or resolved."
            incident_category = "other"

        incident_id = str(uuid.uuid4())
        query = f"{zone} {incident_category}"
        if confidence in {"Sensor-only", "Single unverified report"}:
            query = f"{query} detection verification"
        retrieved = retrieve_sop_chunks(query, top_k=3, threshold=0.2, category=incident_category)
        recommendation = build_recommendation(zone, incident_category, retrieved, confidence=confidence)
        recommendation.update(build_what_would_change_my_mind(incident_category))
        recommendation["llm_mode"] = "template"
        recommendation["source_pack"] = retrieved[0].get("pack") if retrieved and not recommendation.get("status") == "review_required" else None

        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO incidents(id, zone, category, confidence, reason, status, created_at, updated_at, recommendation_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    incident_id,
                    zone,
                    incident_category,
                    confidence,
                    reason,
                    "open",
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    json.dumps(recommendation, ensure_ascii=True),
                ),
            )
            for item in items:
                conn.execute(
                    "UPDATE evidence SET incident_id = ? WHERE id = ?",
                    (incident_id, item["id"]),
                )
            conn.commit()
        append_audit_event(actor="system", event_type="incident_created", payload={"incident_id": incident_id, "confidence": confidence, "zone": zone, "category": incident_category}, incident_id=incident_id)
        incidents.append({"id": incident_id, "zone": zone, "category": incident_category, "confidence": confidence, "reason": reason, "status": "open"})

    return incidents
