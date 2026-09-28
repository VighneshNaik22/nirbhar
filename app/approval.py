from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.db import append_audit_event, get_connection


def _get_incident_recommendation(incident_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT recommendation_json FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        if not row or not row["recommendation_json"]:
            return None
        try:
            return json.loads(row["recommendation_json"])
        except json.JSONDecodeError:
            return None


def create_ticket_for_incident(incident_id: str, action: str, assignee_role: str, decision_reason: str) -> dict:
    """Create a simulated response ticket only after approval or modification is recorded."""
    recommendation = _get_incident_recommendation(incident_id) or {}
    actionable = recommendation.get("steps") or []
    if action == "modify response":
        if decision_reason:
            actionable = [f"{step} | modify_reason: {decision_reason}" for step in actionable] if actionable else [f"Modified response: {decision_reason}"]
    if recommendation.get("status") == "review_required":
        actions = ["Manual review required - no SOP matched"]
    elif actionable:
        actions = []
        for step in actionable:
            if "[SOP:" in step:
                actions.append(step)
            else:
                actions.append(f"{step} | pack: {recommendation.get('source_pack') or 'campus'}")
    elif recommendation.get("status") == "no_action_required":
        actions = []
    else:
        actions = [action]

    payload = {
        "ticket_id": f"TKT-{uuid.uuid4().hex[:8].upper()}",
        "incident_id": incident_id,
        "actions": actions,
        "assignee_role": assignee_role,
        "status": "simulated - not dispatched",
        "decision_reason": decision_reason,
        "source": recommendation.get("source_pack") or "campus",
    }
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, actions TEXT NOT NULL, assignee_role TEXT NOT NULL, status TEXT NOT NULL, decision_reason TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO tickets(id, incident_id, actions, assignee_role, status, decision_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload["ticket_id"],
                incident_id,
                json.dumps(payload["actions"], ensure_ascii=True),
                assignee_role,
                payload["status"],
                decision_reason,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        conn.commit()
    append_audit_event(actor="system", event_type="ticket_created", payload=payload, incident_id=incident_id)
    return payload


def list_tickets() -> list[dict]:
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, actions TEXT NOT NULL, assignee_role TEXT NOT NULL, status TEXT NOT NULL, decision_reason TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        rows = conn.execute(
            "SELECT id, incident_id, actions, assignee_role, status, decision_reason, created_at FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        try:
            item["actions"] = json.loads(item["actions"])
        except json.JSONDecodeError:
            item["actions"] = [item["actions"]]
        output.append(item)
    return output
