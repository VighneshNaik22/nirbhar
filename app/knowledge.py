from __future__ import annotations

import re
from pathlib import Path

from app.config import settings


def _read_pack_files(pack: str) -> list[tuple[str, str, str]]:
    base = Path(__file__).resolve().parent.parent / "sop_packs" / pack
    chunks: list[tuple[str, str, str]] = []
    for path in sorted(base.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        sections: list[tuple[str, str]] = []
        current_title = "Overview"
        current_lines: list[str] = []
        for line in text.splitlines():
            match = re.match(r"^(#+)\s+(.*)$", line.strip())
            if match:
                title = match.group(2).strip()
                if not title:
                    continue
                if current_lines and current_title:
                    sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = title
                current_lines = []
                continue
            if line.strip():
                current_lines.append(line.strip())
        if current_lines and current_title:
            sections.append((current_title, "\n".join(current_lines).strip()))
        for title, body in sections:
            if body and title != "SYNTHETIC SOP FOR DEMO - not an official policy":
                chunks.append((path.name, title, body))
    return chunks


def _pack_documents() -> dict[str, list[dict]]:
    data: dict[str, list[dict]] = {}
    for pack in settings.SOP_PACKS:
        chunks = []
        for file_name, section, body in _read_pack_files(pack):
            chunks.append({
                "id": f"{pack}:{file_name}:{section}",
                "pack": pack,
                "file": file_name,
                "section": section,
                "text": body,
            })
        data[pack] = chunks
    return data


PACK_DOCUMENTS = _pack_documents()


_CATEGORY_FILES = {
    "fire_smoke": "fire_safety.md",
    "ragging": "anti_ragging.md",
    "heat": "ppe_heat.md",
    "ppe": "ppe_heat.md",
}


def filter_sop_chunks_by_category(chunks: list[dict], category: str | None) -> list[dict]:
    """Restrict retrieval candidates before ranking, independent of retrieval backend."""
    file_name = _CATEGORY_FILES.get(category or "")
    if file_name is None:
        return chunks
    return [chunk for chunk in chunks if chunk.get("file") == file_name]


def retrieve_sop_chunks(
    query: str,
    top_k: int = 3,
    threshold: float = 0.3,
    pack: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Return category-scoped SOP chunks or a review-required fallback."""
    active_pack = pack or getattr(settings, "ACTIVE_PACK", "campus")
    docs = PACK_DOCUMENTS.get(active_pack, [])
    if not docs and pack in PACK_DOCUMENTS:
        docs = PACK_DOCUMENTS[pack]
    if not docs:
        return [{"text": "Review Required - no matching SOP found", "score": 0.0, "file": "", "section": "", "pack": active_pack}]

    docs = filter_sop_chunks_by_category(docs, category)
    if not docs:
        return [{"text": "Review Required - no matching SOP found", "score": 0.0, "file": "", "section": "", "pack": active_pack}]

    query_lower = (query or "").lower()
    query_terms = {token for token in re.split(r"[^a-z0-9]+", query_lower) if token}
    alias_map = {
        "worker": {"worker", "workers", "staff", "person", "employee"},
        "ppe": {"ppe", "helmet", "gloves", "eyewear", "safety"},
        "heat": {"heat", "temperature", "hot", "thermal", "ambient"},
        "sensor": {"sensor", "smoke", "temp", "co", "reading"},
        "spike": {"spike", "exceeds", "threshold"},
        "ragging": {"ragging", "bullying", "harassment", "forced", "humiliat", "threatening", "intimidat", "senior", "student"},
        "anti_ragging": {"ragging", "bullying", "harassment", "humiliat", "threatening", "senior student", "senior students"},
    }

    scored = []
    for doc in docs:
        haystack = f"{doc['section']} {doc['text']}".lower()
        haystack_tokens = {token for token in re.split(r"[^a-z0-9]+", haystack) if token}
        score = 0.0
        for raw in query_terms:
            expansions = {raw}
            for key, values in alias_map.items():
                if raw in values or raw == key:
                    expansions |= values
                    expansions.add(key)
            if any(term in haystack_tokens for term in expansions):
                score += 1.0
        if query_lower and "ragging" in query_lower:
            if "anti_ragging" in doc["file"].lower() or "ragging" in haystack:
                score += 1.5
        if not query_terms:
            score = 0.0
        scored.append({
            "id": doc["id"],
            "score": round(score / max(len(query_terms) or 1, 1), 4),
            "file": doc["file"],
            "section": doc["section"],
            "text": doc["text"],
            "pack": doc["pack"],
        })

    scored.sort(key=lambda item: item["score"], reverse=True)
    ranked = [item for item in scored if item["score"] >= threshold]
    if not ranked:
        return [{"text": "Review Required - no matching SOP found", "score": 0.0, "file": "", "section": "", "pack": active_pack}]
    return ranked[:top_k]
