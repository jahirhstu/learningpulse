"""Behavior checks for validation, configuration, and mixed-batch routing."""

import io
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from learningpulse.config import load_config
from learningpulse.generator import JsonLogFormatter, generate_events, write_jsonl
from learningpulse.validation import validate_record


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.record = asdict(next(generate_events(1, seed=42)))

    def test_generated_records_are_valid(self):
        for event in generate_events(1000, seed=42):
            self.assertEqual(validate_record(asdict(event)), [])

    def test_invalid_fields_have_reasons(self):
        cases = [
            ("event_id", None), ("learner_id", ""), ("assessment_id", "bad-id"),
            ("occurred_at", "not-a-time"), ("ingested_at", "2026-10-16T12:00:00"),
            ("event_type", "unknown"), ("subject", "unknown"),
            ("score", -1), ("score", "80"), ("score", True),
            ("max_score", 0), ("max_score", -1), ("max_score", False),
            ("score", self.record["max_score"] + 1),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                reasons = validate_record({**self.record, field: value})
                self.assertTrue(any(reason.startswith(field + ":") for reason in reasons))

    def test_missing_fields_and_multiple_failures(self):
        reasons = validate_record({})
        self.assertEqual(len(reasons), 9)

    def test_zero_and_maximum_scores_are_valid(self):
        for score in (0, self.record["max_score"]):
            self.assertEqual(validate_record({**self.record, "score": score}), [])

    def test_ingestion_cannot_precede_completion(self):
        self.record["occurred_at"] = "2026-10-16T12:00:00+00:00"
        self.record["ingested_at"] = "2026-10-16T11:00:00+00:00"
        self.assertIn("ingested_at: must not precede occurred_at", validate_record(self.record))


class RoutingTests(unittest.TestCase):
    def test_mixed_batch_continues_and_logs_each_rejection(self):
        records = [asdict(event) for event in generate_events(6, seed=42)]
        records[1]["score"] = -1
        records[3].pop("learner_id")
        records[4]["ingested_at"] = "bad-time"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "raw/events.jsonl"
            quarantine = Path(directory) / "quarantine/invalid_events.jsonl"
            with self.assertLogs("learningpulse.generator", level="INFO") as captured:
                count = write_jsonl(iter(records), output, quarantine)
            valid = [json.loads(line) for line in output.read_text().splitlines()]
            invalid = [json.loads(line) for line in quarantine.read_text().splitlines()]
            self.assertEqual(count, 3)
            self.assertEqual(len(valid) + len(invalid), 6)
            self.assertEqual(valid[-1], records[-1])
            self.assertTrue(all(entry["reasons"] for entry in invalid))
            logs = [json.loads(JsonLogFormatter().format(record)) for record in captured.records]
            self.assertEqual([entry["event_id"] for entry in logs[:-1]], [records[i]["event_id"] for i in (1, 3, 4)])
            self.assertTrue(all(entry["status"] == "rejected" and entry["reason"] for entry in logs[:-1]))
            self.assertEqual((logs[-1]["accepted"], logs[-1]["rejected"], logs[-1]["total"]), (3, 3, 6))
            with self.assertLogs("learningpulse.generator", level="INFO"):
                write_jsonl([records[1]], output, quarantine)
            self.assertEqual(len(quarantine.read_text().splitlines()), 4)

    def test_same_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            write_jsonl([], Path("same.jsonl"), Path("same.jsonl"))


class ConfigTests(unittest.TestCase):
    def test_environment_values(self):
        config = load_config([], environ={
            "LEARNINGPULSE_RECORD_COUNT": "12", "LEARNINGPULSE_OUTPUT_PATH": "custom/events.jsonl",
            "LEARNINGPULSE_QUARANTINE_PATH": "custom/invalid.jsonl", "LEARNINGPULSE_SEED": "42",
        })
        self.assertEqual((config.record_count, config.seed), (12, 42))
        self.assertEqual(config.output_path, Path("custom/events.jsonl"))
        self.assertEqual(config.quarantine_path, Path("custom/invalid.jsonl"))

    def test_cli_overrides_environment_including_zero(self):
        config = load_config(["--count", "0", "--seed", "0", "--output", "cli.jsonl"], environ={
            "LEARNINGPULSE_RECORD_COUNT": "bad", "LEARNINGPULSE_SEED": "bad",
            "LEARNINGPULSE_OUTPUT_PATH": "env.jsonl",
        })
        self.assertEqual((config.record_count, config.seed, config.output_path), (0, 0, Path("cli.jsonl")))

    def test_bad_configuration_fails_before_processing(self):
        from contextlib import redirect_stderr

        for argv, env in [
            (["--count", "-1"], {}), ([], {"LEARNINGPULSE_RECORD_COUNT": "bad"}),
            (["--output", "same", "--quarantine", "same"], {}),
        ]:
            with self.subTest(argv=argv, env=env), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                load_config(argv, environ=env)


if __name__ == "__main__":
    unittest.main()
