"""Generate realistic synthetic LearningPulse assessment events as JSON Lines."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence
from uuid import UUID, uuid4

from learningpulse.config import default_output_path, load_config
from learningpulse.validation import SUBJECTS, validate_record

logger = logging.getLogger(__name__)
MAX_SCORES: tuple[int, ...] = (20, 25, 50, 100)


@dataclass(frozen=True)
class AssessmentEvent:
    """Version 1 assessment-completion event."""

    event_id: str
    learner_id: str
    assessment_id: str
    subject: str
    score: int
    max_score: int
    event_type: str
    occurred_at: str
    ingested_at: str


def _stable_uuid(rng: random.Random) -> str:
    """Return a valid UUID generated from the seeded random source."""

    return str(UUID(int=rng.getrandbits(128), version=4))


def generate_events(
    count: int = 1_000,
    *,
    seed: int | None = None,
    generated_at: datetime | None = None,
) -> Iterator[AssessmentEvent]:
    """Yield synthetic events with plausible scores and ingestion latency."""

    if count < 0:
        raise ValueError("count must be non-negative")

    rng = random.Random(seed)
    anchor = generated_at or datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        raise ValueError("generated_at must include timezone information")

    learner_ids = [_stable_uuid(rng) for _ in range(max(50, min(250, count)))]
    assessment_ids = {
        subject: [_stable_uuid(rng) for _ in range(8)] for subject in SUBJECTS
    }

    for _ in range(count):
        subject = rng.choice(SUBJECTS)
        max_score = rng.choice(MAX_SCORES)
        # A clipped normal distribution produces varied, realistic results.
        percentage = min(1.0, max(0.0, rng.gauss(0.74, 0.16)))
        score = round(max_score * percentage)
        occurred_at = anchor - timedelta(
            seconds=rng.randint(0, 7 * 24 * 60 * 60)
        )
        ingested_at = occurred_at + timedelta(seconds=rng.randint(1, 180))

        yield AssessmentEvent(
            event_id=str(uuid4()) if seed is None else _stable_uuid(rng),
            learner_id=rng.choice(learner_ids),
            assessment_id=rng.choice(assessment_ids[subject]),
            subject=subject,
            score=score,
            max_score=max_score,
            event_type="assessment_completed",
            occurred_at=occurred_at.isoformat(),
            ingested_at=ingested_at.isoformat(),
        )


class JsonLogFormatter(logging.Formatter):
    """Serialize custom LogRecord fields into one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "event_id": getattr(record, "event_id", None),
            "status": getattr(record, "status", None),
            "reason": getattr(record, "reason", None),
        }
        for field in ("accepted", "rejected", "duplicates", "total"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload)


class ExistingOutputError(ValueError):
    """Accepted output is unsafe to append to without manual repair."""


def _read_accepted_ids(output_path: Path) -> tuple[set[str], bool]:
    """Validate existing output before writes; retain IDs and newline state only."""
    seen: set[str] = set()
    needs_newline = False
    try:
        output_file = output_path.open(encoding="utf-8")
    except FileNotFoundError:
        return seen, needs_newline
    try:
        with output_file:
            for line_number, line in enumerate(output_file, start=1):
                try:
                    record = json.loads(line)
                except ValueError as error:
                    raise ExistingOutputError(
                        f"{output_path}: line {line_number}: invalid JSON"
                    ) from error
                reasons = validate_record(record) if isinstance(record, dict) else ["expected a JSON object"]
                if reasons:
                    raise ExistingOutputError(
                        f"{output_path}: line {line_number}: {'; '.join(reasons)}"
                    )
                event_id = record["event_id"]
                if event_id in seen:
                    raise ExistingOutputError(
                        f"{output_path}: line {line_number}: duplicate event_id {event_id}"
                    )
                seen.add(event_id)
                needs_newline = not line.endswith("\n")
    except UnicodeError as error:
        raise ExistingOutputError(f"{output_path}: invalid UTF-8") from error
    return seen, needs_newline


def write_jsonl(
    events: Iterable[AssessmentEvent | Mapping[str, object]],
    output_path: Path,
    quarantine_path: Path = Path("data/quarantine/invalid_events.jsonl"),
) -> int:
    """Append new valid IDs, quarantine invalid records, return newly accepted count."""
    if output_path.resolve() == quarantine_path.resolve():
        raise ValueError("output and quarantine paths must differ")

    seen, needs_newline = _read_accepted_ids(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    written = rejected = duplicates = 0
    with output_path.open("a", encoding="utf-8") as output_file, quarantine_path.open("a", encoding="utf-8") as quarantine_file:
        for event in events:
            record = asdict(event) if isinstance(event, AssessmentEvent) else dict(event)
            reasons = validate_record(record)
            if reasons:
                quarantine_file.write(json.dumps({"record": record, "status": "rejected", "reasons": reasons}, separators=(",", ":")) + "\n")
                rejected += 1
                logger.warning("Assessment event rejected", extra={
                    "event_id": record.get("event_id"), "status": "rejected", "reason": reasons,
                })
                continue
            event_id = record["event_id"]
            if event_id in seen:
                duplicates += 1
                logger.info("Duplicate assessment event skipped", extra={
                    "event_id": event_id, "status": "duplicate",
                    "reason": "event_id already accepted; keeping first record",
                })
                continue
            if needs_newline:
                output_file.write("\n")
                needs_newline = False
            output_file.write(json.dumps(record, separators=(",", ":")) + "\n")
            seen.add(event_id)
            written += 1
    logger.info("Assessment batch completed", extra={
        "event_id": None, "status": "completed", "reason": None,
        "accepted": written, "rejected": rejected, "duplicates": duplicates,
        "total": written + rejected + duplicates,
    })
    return written


def main(argv: Sequence[str] | None = None) -> int:
    config = load_config(argv)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    try:
        write_jsonl(
            generate_events(config.record_count, seed=config.seed),
            config.output_path,
            config.quarantine_path,
        )
    except (OSError, ExistingOutputError) as error:
        logger.error("Assessment batch failed", extra={
            "event_id": None, "status": "failed", "reason": str(error),
        })
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
