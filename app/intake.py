from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.db import append_audit_event, get_connection
from app.schema import EvidenceCreate, ReportInput, SensorInput


def _normalize_category(sensor_type: str | None, description: str) -> str:
    text = (description or "").lower()
    if re.search(r"\bsmoke\b|\bsmoky\b", text) or sensor_type == "smoke":
        return "fire_smoke"
    ragging_markers = [
        "ragging",
        "bullying",
        "harassment",
        "forced",
        "humiliat",
        "intimidat",
        "threatening",
        "senior student",
        "senior students",
    ]
    if any(marker in text for marker in ragging_markers):
        return "ragging"
    if "heat" in text or sensor_type == "temp":
        return "heat"
    if "ppe" in text or "helmet" in text or "gloves" in text:
        return "ppe"
    return "other"


def _is_threshold_exceeded(sensor_type: str, value: float) -> bool:
    thresholds = {"smoke": 0.6, "temp": 60.0, "co": 35.0}
    return value > thresholds.get(sensor_type, float("inf"))


def normalize_report(payload: ReportInput) -> dict:
    timestamp = payload.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = {
        "id": str(uuid.uuid4()),
        "source_type": payload.source_type,
        "zone": payload.zone,
        "category": _normalize_category(None, payload.description),
        "description": payload.description,
        "sensor_type": None,
        "sensor_value": None,
        "severity_hint": payload.severity_hint,
        "reporter_role": payload.reporter_role,
        "timestamp": timestamp,
        "incident_id": None,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO evidence(id, source_type, zone, category, description, sensor_type, sensor_value, severity_hint, reporter_role, timestamp, incident_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence["id"],
                evidence["source_type"],
                evidence["zone"],
                evidence["category"],
                evidence["description"],
                evidence["sensor_type"],
                evidence["sensor_value"],
                evidence["severity_hint"],
                evidence["reporter_role"],
                evidence["timestamp"],
                evidence["incident_id"],
            ),
        )
        conn.commit()
    append_audit_event(actor="system", event_type="evidence_received", payload={"evidence_id": evidence["id"], "source_type": payload.source_type, "zone": payload.zone}, incident_id=None)
    append_audit_event(actor="system", event_type="incident_created", payload={"evidence_id": evidence["id"], "source_type": payload.source_type, "zone": payload.zone, "confidence": "Single unverified report"}, incident_id=None)
    return {"success": True, "evidence": evidence}


def normalize_sensor(payload: SensorInput) -> dict:
    sensor_type = payload.sensor_type
    sensor_value = float(payload.value)
    category = _normalize_category(sensor_type, f"sensor {sensor_type} spike")
    timestamp = payload.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = {
        "id": str(uuid.uuid4()),
        "source_type": "sensor",
        "zone": payload.zone,
        "category": category,
        "description": f"{sensor_type} reading {sensor_value} triggered threshold check",
        "sensor_type": sensor_type,
        "sensor_value": sensor_value,
        "severity_hint": 5 if _is_threshold_exceeded(sensor_type, sensor_value) else 1,
        "reporter_role": "sensor",
        "timestamp": timestamp,
        "incident_id": None,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO evidence(id, source_type, zone, category, description, sensor_type, sensor_value, severity_hint, reporter_role, timestamp, incident_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence["id"],
                evidence["source_type"],
                evidence["zone"],
                evidence["category"],
                evidence["description"],
                evidence["sensor_type"],
                evidence["sensor_value"],
                evidence["severity_hint"],
                evidence["reporter_role"],
                evidence["timestamp"],
                evidence["incident_id"],
            ),
        )
        conn.commit()
    append_audit_event(actor="system", event_type="evidence_received", payload={"evidence_id": evidence["id"], "source_type": "sensor", "zone": payload.zone, "sensor_type": sensor_type}, incident_id=None)
    append_audit_event(actor="system", event_type="incident_created", payload={"evidence_id": evidence["id"], "source_type": "sensor", "zone": payload.zone, "sensor_type": sensor_type, "confidence": "Sensor-only"}, incident_id=None)
    return {"success": True, "evidence": evidence}
