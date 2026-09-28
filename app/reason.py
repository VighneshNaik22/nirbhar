from __future__ import annotations

from app.knowledge import retrieve_sop_chunks


def build_recommendation(
    zone: str,
    category: str,
    retrieved_chunks: list[dict] | None = None,
    confidence: str = "Confirmed",
) -> dict:
    """Return a recommendation with SOP citations or a review-required fallback."""
    if confidence == "Normal/Below threshold":
        return {
            "status": "no_action_required",
            "message": "No action required - monitor",
            "steps": [],
            "cited_chunks": [],
            "source_pack": None,
            "missing_evidence": [],
        }

    chunks = retrieved_chunks or []
    if not chunks:
        recommendation = {
            "status": "review_required",
            "message": "Review Required - no matching SOP found",
            "steps": [],
            "cited_chunks": [],
            "source_pack": None,
            "missing_evidence": ["Missing: no corroborating evidence"],
        }
        return filter_recommendation_by_confidence(recommendation, confidence)

    steps: list[str] = []
    cited_chunks: list[dict] = []
    source_pack = chunks[0].get("pack") or "campus"
    for chunk in chunks:
        section = chunk.get("section", "Unknown section")
        file_name = chunk.get("file", "unknown.md")
        text = chunk.get("text", "").strip()
        if not text:
            continue
        steps.append(f"{text} [SOP: {file_name} > {section}]")
        cited_chunks.append({
            "file": file_name,
            "section": section,
            "text": text,
            "pack": chunk.get("pack") or source_pack,
        })

    recommendation = {
        "status": "ok",
        "steps": steps,
        "message": "Recommended action based on retrieved SOP content.",
        "cited_chunks": cited_chunks,
        "source_pack": source_pack,
        "missing_evidence": ["Missing: no corroborating evidence"],
    }
    return filter_recommendation_by_confidence(recommendation, confidence)


def filter_recommendation_by_confidence(recommendation: dict, confidence: str) -> dict:
    """Gate generated action steps on incident confidence after recommendation generation."""
    if confidence not in {"Sensor-only", "Single unverified report"}:
        return recommendation

    allowed = "detection & verification"
    recommendation["steps"] = [
        step for step in recommendation.get("steps", []) if allowed in step.lower()
    ]
    recommendation["cited_chunks"] = [
        chunk for chunk in recommendation.get("cited_chunks", [])
        if chunk.get("section", "").lower() == allowed
    ]
    return recommendation


def build_what_would_change_my_mind(category: str) -> dict:
    """Return clear escalation, de-escalation, and evidence-gaps guidance."""
    if category == "fire_smoke":
        return {
            "escalate_if": [
                "Escalate if a second sensor in an adjacent zone exceeds threshold",
                "Escalate if a fire warden confirms smoke near the same room",
            ],
            "de_escalate_if": [
                "De-escalate if smoke level returns below threshold and no human report remains",
                "De-escalate if the report is resolved and the room is clear",
            ],
            "missing_evidence": [
                "Missing: no human confirmation yet",
                "Missing: no second-source verification",
            ],
        }
    return {
        "escalate_if": ["Escalate if a second independent report confirms the concern"],
        "de_escalate_if": ["De-escalate if the concern is resolved and no thresholds are exceeded"],
        "missing_evidence": ["Missing: no corroborating human or sensor evidence"],
    }
