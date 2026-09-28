from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import append_audit_event, get_connection, init_db
from app.intake import normalize_report, normalize_sensor
from app.schema import ReportInput, SensorInput


def load_demo() -> list[dict]:
    """Seed three-room scenario and anti-ragging evidence for the UI demo."""
    init_db()
    now = datetime.now(timezone.utc)

    def timestamp(minutes_ago: int) -> str:
        return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_connection() as conn:
        conn.execute("DELETE FROM evidence")
        conn.execute("DELETE FROM incidents")
        conn.commit()

    room_a = [
        ReportInput(
            zone="Hostel-A-Room-204",
            reporter_role="student",
            description="Strong smoke smell near the room and I think there is a fire.",
            severity_hint=4,
            source_type="student_report",
            timestamp=timestamp(7),
        ),
        ReportInput(
            zone="Hostel-A-Room-204",
            reporter_role="guard",
            description="Guard observed smoke in the corridor near the room.",
            severity_hint=3,
            source_type="guard_report",
            timestamp=timestamp(5),
        ),
    ]
    for payload in room_a:
        normalize_report(payload)

    normalize_sensor(SensorInput(zone="Hostel-A-Room-204", sensor_type="smoke", value=0.8, timestamp=timestamp(3)))

    normalize_sensor(SensorInput(zone="Hostel-B-Room-110", sensor_type="smoke", value=0.7, timestamp=timestamp(6)))

    normalize_sensor(SensorInput(zone="Hostel-C-Room-305", sensor_type="smoke", value=0.2, timestamp=timestamp(4)))
    normalize_report(ReportInput(zone="Hostel-C-Room-305", reporter_role="student", description="Incense smell, resolved.", severity_hint=1, source_type="student_report", timestamp=timestamp(2)))

    normalize_report(ReportInput(zone="Hostel-D-Common-Area", reporter_role="student", description="A senior student is threatening and bullying me in the hallway.", severity_hint=4, source_type="student_report", timestamp=timestamp(1)))
    return []


def reset_demo() -> None:
    init_db()
    with get_connection() as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        for table in ("tickets", "approvals", "saved_recommendations", "recommendations", "evidence", "incidents"):
            if table in existing_tables:
                conn.execute(f"DELETE FROM {table}")
        conn.commit()
    append_audit_event(actor="system", event_type="demo_reset", payload={"scope": "demo"})
