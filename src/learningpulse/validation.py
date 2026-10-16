"""Validate assessment records without raising for bad field values."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping
from uuid import UUID

SUBJECTS: tuple[str, ...] = (
    "mathematics", "science", "english", "history", "computer_science",
)


def validate_record(record: Mapping[str, object]) -> list[str]:
    """Return all rejection reasons; an empty list means the record is valid."""
    reasons: list[str] = []
    for field in ("event_id", "learner_id", "assessment_id"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"{field}: required non-empty UUID string")
        else:
            try:
                UUID(value)
            except ValueError:
                reasons.append(f"{field}: invalid UUID")

    timestamps: dict[str, datetime] = {}
    for field in ("occurred_at", "ingested_at"):
        value = record.get(field)
        if not isinstance(value, str) or "T" not in value:
            reasons.append(f"{field}: required ISO 8601 timestamp with timezone")
            continue
        try:
            timestamp = datetime.fromisoformat(value)
            if timestamp.utcoffset() is None:
                raise ValueError("missing timezone")
            timestamps[field] = timestamp
        except ValueError:
            reasons.append(f"{field}: invalid ISO 8601 timestamp or missing timezone")
    if len(timestamps) == 2 and timestamps["ingested_at"] < timestamps["occurred_at"]:
        reasons.append("ingested_at: must not precede occurred_at")

    if record.get("event_type") != "assessment_completed":
        reasons.append("event_type: must be assessment_completed")
    if record.get("subject") not in SUBJECTS:
        reasons.append("subject: must be an allowed assessment subject")

    score, maximum = record.get("score"), record.get("max_score")
    # bool subclasses int, but is not a valid assessment score.
    if type(score) is not int:
        reasons.append("score: must be an integer")
    elif score < 0:
        reasons.append("score: must be >= 0")
    if type(maximum) is not int:
        reasons.append("max_score: must be an integer")
    elif maximum <= 0:
        reasons.append("max_score: must be > 0")
    if type(score) is int and type(maximum) is int and score > maximum:
        reasons.append("score: must be <= max_score")
    return reasons
