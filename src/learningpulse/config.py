"""Runtime configuration. CLI values take precedence over environment values."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence


def default_output_path(for_date: date | None = None) -> Path:
    partition_date = for_date or datetime.now().astimezone().date()
    return Path("data/raw") / f"assessment_events/date={partition_date.isoformat()}" / "events.jsonl"


@dataclass(frozen=True)
class GeneratorConfig:
    record_count: int
    output_path: Path
    quarantine_path: Path
    seed: int | None


def load_config(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> GeneratorConfig:
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description="Generate and validate assessment events.")
    parser.add_argument("--count", "--record-count", dest="record_count", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quarantine", type=Path)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args(argv)
    try:
        count = args.record_count if args.record_count is not None else int(env.get("LEARNINGPULSE_RECORD_COUNT", "1000"))
        seed = args.seed if args.seed is not None else (
            int(env["LEARNINGPULSE_SEED"]) if "LEARNINGPULSE_SEED" in env else None
        )
    except ValueError:
        parser.error("record count and seed must be integers")
    if count < 0:
        parser.error("record count must be non-negative")
    output = args.output if args.output is not None else Path(env.get("LEARNINGPULSE_OUTPUT_PATH", str(default_output_path())))
    quarantine = args.quarantine if args.quarantine is not None else Path(env.get("LEARNINGPULSE_QUARANTINE_PATH", "data/quarantine/invalid_events.jsonl"))
    if output.resolve() == quarantine.resolve():
        parser.error("output and quarantine paths must differ")
    return GeneratorConfig(count, output, quarantine, seed)
