from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


EvidenceSource = Literal["student_report", "guard_report", "warden_report", "sensor"]
EvidenceCategory = Literal["fire_smoke", "ragging", "heat", "ppe", "other"]


class EvidenceCreate(BaseModel):
    """Unified evidence schema for all incoming signals."""

    source_type: EvidenceSource
    zone: str = Field(..., min_length=1)
    category: EvidenceCategory | None = None
    description: str = Field(..., min_length=1)
    sensor_type: Literal["smoke", "temp", "co"] | None = None
    sensor_value: float | None = None
    severity_hint: int = Field(default=1, ge=1, le=5)
    reporter_role: str | None = None
    timestamp: str | None = None
    incident_id: str | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return utc_now()
        return value


class EvidenceRecord(BaseModel):
    id: str
    source_type: EvidenceSource
    zone: str
    category: EvidenceCategory
    description: str
    sensor_type: str | None = None
    sensor_value: float | None = None
    severity_hint: int
    reporter_role: str | None = None
    timestamp: str
    incident_id: str | None = None


class ReportInput(BaseModel):
    zone: str = Field(..., min_length=1)
    reporter_role: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity_hint: int = Field(default=1, ge=1, le=5)
    source_type: EvidenceSource = "student_report"
    timestamp: str | None = None


class SensorInput(BaseModel):
    zone: str = Field(..., min_length=1)
    sensor_type: Literal["smoke", "temp", "co"]
    value: float
    timestamp: str | None = None
