from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.approval import create_ticket_for_incident, list_tickets
from app.config import settings
from app.correlate import correlate_evidence
from app.db import get_connection, init_db, verify_audit_chain
from app.demo import load_demo, reset_demo
from app.intake import normalize_report, normalize_sensor
from app.knowledge import PACK_DOCUMENTS, retrieve_sop_chunks
from app.schema import ReportInput, SensorInput

app = FastAPI(title=settings.APP_NAME, version="0.1.0")
init_db()


@app.get("/api/health")
def health() -> JSONResponse:
    """Return app health and dependency status summary."""
    llm_status = "online"
    retriever = "chroma"
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code != 200:
            llm_status = "offline - template mode"
            retriever = "bm25-fallback"
    except Exception:
        llm_status = "offline - template mode"
        retriever = "bm25-fallback"
    return JSONResponse(
        {
            "status": "ok",
            "app": settings.APP_NAME,
            "llm_model": settings.OLLAMA_MODEL,
            "llm_status": llm_status,
            "retriever": retriever,
            "packs": list(settings.SOP_PACKS),
        }
    )


@app.post("/api/reports")
def submit_report(payload: ReportInput) -> dict:
    """Accept typed human reports and normalize them into the evidence schema."""
    try:
        return normalize_report(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/sensors")
def submit_sensor(payload: SensorInput) -> dict:
    """Accept simulated sensor readings and normalize them into the evidence schema."""
    try:
        return normalize_sensor(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/audit")
def list_audit() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, ts, actor, event_type, incident_id, payload_json, prev_hash, hash FROM audit_log ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/audit/verify")
def audit_verify() -> dict:
    return verify_audit_chain()


@app.post("/api/pack/activate")
def activate_pack(payload: dict) -> dict:
    pack = payload.get("pack", "campus")
    if pack not in settings.SOP_PACKS:
        raise HTTPException(status_code=400, detail=f"Unsupported pack: {pack}")
    settings.ACTIVE_PACK = pack
    return {"pack": pack, "status": "active"}


@app.post("/api/knowledge/retrieve")
def retrieve_endpoint(payload: dict) -> dict:
    query = payload.get("query", "")
    top_k = int(payload.get("top_k", 3))
    pack = payload.get("pack")
    category = payload.get("category")
    results = retrieve_sop_chunks(query, top_k=top_k, threshold=0.3, pack=pack, category=category)
    return {"query": query, "results": results}


@app.post("/api/incidents/{incident_id}/approve")
def approve_incident(incident_id: str, payload: dict) -> dict:
    reason = (payload.get("reason") or "").strip()
    decision = (payload.get("decision") or "approve").strip().lower()
    ticket = create_ticket_for_incident(incident_id, decision, "officer", reason)
    return {"incident_id": incident_id, "decision": decision, "status": ticket["status"], "ticket_id": ticket["ticket_id"]}


@app.post("/api/incidents/{incident_id}/modify")
def modify_incident(incident_id: str, payload: dict) -> dict:
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason is required for modification")
    ticket = create_ticket_for_incident(incident_id, "modify response", "officer", reason)
    return {"incident_id": incident_id, "decision": "modify", "status": ticket["status"], "ticket_id": ticket["ticket_id"]}


@app.post("/api/incidents/{incident_id}/reject")
def reject_incident(incident_id: str, payload: dict) -> dict:
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason is required for rejection")
    ticket = create_ticket_for_incident(incident_id, "do not dispatch", "officer", reason)
    return {"incident_id": incident_id, "decision": "reject", "status": ticket["status"], "ticket_id": ticket["ticket_id"]}


@app.get("/api/incidents/{incident_id}")
def incident_detail(incident_id: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, zone, category, confidence, reason, status, created_at, updated_at, recommendation_json FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        evidence_rows = conn.execute(
            "SELECT id, source_type, zone, category, description, sensor_type, sensor_value, severity_hint, reporter_role, timestamp FROM evidence WHERE incident_id = ? ORDER BY timestamp ASC",
            (incident_id,),
        ).fetchall()

    recommendation = json.loads(row["recommendation_json"]) if row["recommendation_json"] else {
        "status": "review_required",
        "message": "Review Required - no matching SOP found",
        "steps": [],
        "missing_evidence": ["Missing: no corroborating evidence"],
        "llm_mode": "template",
    }
    if "missing_evidence" not in recommendation:
        recommendation["missing_evidence"] = ["Missing: no corroborating evidence"]
    if "llm_mode" not in recommendation:
        recommendation["llm_mode"] = "template"

    return {
        "incident": {
            "id": row["id"],
            "zone": row["zone"],
            "category": row["category"],
            "confidence": row["confidence"],
            "reason": row["reason"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
        "evidence": [dict(item) for item in evidence_rows],
        "recommendation": recommendation,
    }


@app.get("/api/tickets")
def tickets() -> list[dict]:
    return list_tickets()


@app.get("/api/incidents")
def incidents() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, zone, category, confidence, reason, status, created_at, updated_at FROM incidents ORDER BY created_at ASC"
        ).fetchall()
    results = [dict(row) for row in rows]
    if not results:
        return correlate_evidence()
    return results


@app.get("/api/role-view")
@app.get("/api/role-view/{role}")
def role_view(role: str | None = None) -> dict:
    requested_role = (role or "default").lower()
    incident_rows = incidents()
    if requested_role in {"all", "officer"}:
        filtered = incident_rows
    elif requested_role == "student":
        filtered = []
    elif requested_role == "administrator":
        filtered = incident_rows
    elif requested_role == "warden":
        filtered = [item for item in incident_rows if item.get("confidence") in {"Confirmed", "Sensor-only", "Single unverified report"}]
    else:
        filtered = [item for item in incident_rows if item.get("zone", "").lower().startswith(requested_role.lower())]

    summary = {"total": len(incident_rows), "visible": len(filtered)}
    if requested_role == "student":
        summary["status"] = "student view: status summary only"
        return {"role": requested_role, "count": 0, "incidents": [], "summary": summary}
    if requested_role == "administrator":
        summary["audit"] = len(list_audit())
        summary["packs"] = list(settings.SOP_PACKS)
    return {"role": requested_role, "count": len(filtered), "incidents": filtered, "summary": summary}


@app.get("/api/memory/search")
def memory_search(query: str | None = None) -> dict:
    q = (query or "").strip().lower()
    if not q:
        return {"query": q, "results": []}

    with get_connection() as conn:
        evidence_rows = conn.execute(
            "SELECT id, zone, source_type, category, description, reporter_role, timestamp FROM evidence ORDER BY timestamp DESC"
        ).fetchall()
        incident_rows = conn.execute(
            "SELECT id, zone, category, confidence, reason, status, created_at FROM incidents ORDER BY created_at DESC"
        ).fetchall()

    matches: list[dict] = []
    for row in evidence_rows:
        haystack = " ".join([
            row["zone"], row["source_type"], row["category"], row["description"], row["reporter_role"] or ""
        ]).lower()
        if q in haystack:
            matches.append({
                "type": "evidence",
                "id": row["id"],
                "zone": row["zone"],
                "category": row["category"],
                "source_type": row["source_type"],
                "timestamp": row["timestamp"],
                "snippet": row["description"],
            })

    for row in incident_rows:
        haystack = " ".join([
            row["zone"], row["category"], row["confidence"], row["reason"], row["status"]
        ]).lower()
        if q in haystack:
            matches.append({
                "type": "incident",
                "id": row["id"],
                "zone": row["zone"],
                "category": row["category"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "timestamp": row["created_at"],
                "snippet": row["reason"],
            })

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in matches:
        key = f"{item['type']}::{item['id']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return {"query": q, "results": deduped[:20]}


@app.get("/api/graph")
def graph() -> dict:
    with get_connection() as conn:
        evidence = conn.execute(
            "SELECT id, zone, source_type, category, description FROM evidence ORDER BY timestamp ASC LIMIT 20"
        ).fetchall()
    nodes = []
    edges = []
    for item in evidence:
        nodes.append({"id": item["id"], "type": "evidence", "label": item["source_type"], "zone": item["zone"]})
        edges.append({"from": item["id"], "to": item["zone"], "label": item["category"]})
    nodes.append({"id": "zone:Hostel-A-Room-204", "type": "zone", "label": "Hostel-A-Room-204"})
    nodes.append({"id": "zone:Hostel-B-Room-110", "type": "zone", "label": "Hostel-B-Room-110"})
    nodes.append({"id": "zone:Hostel-C-Room-305", "type": "zone", "label": "Hostel-C-Room-305"})
    return {"nodes": nodes, "edges": edges}


@app.get("/api/heatmap")
def heatmap() -> dict:
    return {
        "label": "SYNTHETIC - illustrative, not predictive",
        "zones": [
            {"zone": "Hostel-A-Room-204", "risk": "High"},
            {"zone": "Hostel-B-Room-110", "risk": "Medium"},
            {"zone": "Hostel-C-Room-305", "risk": "Low"},
        ],
    }


@app.post("/api/demo/load")
def demo_load() -> dict:
    load_demo()
    return {"status": "loaded"}


@app.post("/api/demo/reset")
def demo_reset() -> dict:
    reset_demo()
    return {"status": "reset"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "NIRBHAR is running."}
