"""Behavior checks for validation, configuration, and mixed-batch routing."""

import io
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from learningpulse.config import load_config
from learningpulse.generator import ExistingOutputError, JsonLogFormatter, generate_events, main, write_jsonl
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


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "events.jsonl"
        self.quarantine = Path(self.directory.name) / "invalid.jsonl"
        self.records = [asdict(event) for event in generate_events(3, seed=42)]

    def write(self, records):
        with self.assertLogs("learningpulse.generator", level="INFO") as captured:
            count = write_jsonl(iter(records), self.output, self.quarantine)
        logs = [json.loads(JsonLogFormatter().format(record)) for record in captured.records]
        return count, logs

    def read_output(self):
        return [json.loads(line) for line in self.output.read_text().splitlines()]

    def test_replaying_same_batch_preserves_output_exactly(self):
        count, _ = self.write(self.records)
        self.assertEqual(count, 3)
        original = self.output.read_bytes()
        count, logs = self.write(self.records)
        self.assertEqual(count, 0)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(len({record["event_id"] for record in self.read_output()}), 3)
        self.assertEqual(self.quarantine.read_text(), "")
        self.assertEqual([entry["event_id"] for entry in logs[:-1]], [record["event_id"] for record in self.records])
        self.assertTrue(all(entry["status"] == "duplicate" and entry["reason"] for entry in logs[:-1]))
        self.assertEqual({key: logs[-1][key] for key in ("accepted", "rejected", "duplicates", "total")},
                         {"accepted": 0, "rejected": 0, "duplicates": 3, "total": 3})

    def test_duplicates_within_batch_and_overlapping_runs_keep_first(self):
        first, second, third = self.records
        changed = {**first, "score": (first["score"] + 1) % (first["max_score"] + 1)}
        count, logs = self.write([first, changed, second])
        self.assertEqual((count, logs[-1]["duplicates"]), (2, 1))
        count, logs = self.write([changed, second, third])
        self.assertEqual((count, logs[-1]["duplicates"]), (1, 2))
        self.assertEqual(self.read_output(), self.records)

    def test_invalid_records_do_not_reserve_ids(self):
        first = self.records[0]
        invalid = {**first, "score": -1}
        count, logs = self.write([invalid, first, first, invalid])
        self.assertEqual(count, 1)
        self.assertEqual(self.read_output(), [first])
        self.assertEqual(len(self.quarantine.read_text().splitlines()), 2)
        self.assertEqual((logs[-1]["accepted"], logs[-1]["rejected"], logs[-1]["duplicates"], logs[-1]["total"]), (1, 2, 1, 4))

    def test_bad_existing_output_does_not_modify_either_file(self):
        valid_line = json.dumps(self.records[0]) + "\n"
        cases = [b"not-json\n", b"[]\n", b"{}\n", b"\xff", b"\n",
                 (valid_line * 2).encode(), (valid_line + "broken\n").encode()]
        for contents in cases:
            with self.subTest(contents=contents):
                self.output.write_bytes(contents)
                self.quarantine.write_text("existing quarantine\n")
                with self.assertRaises(ExistingOutputError):
                    write_jsonl(self.records, self.output, self.quarantine)
                self.assertEqual(self.output.read_bytes(), contents)
                self.assertEqual(self.quarantine.read_text(), "existing quarantine\n")

    def test_cli_logs_corrupt_output_failure(self):
        self.output.write_text("broken\n")
        with self.assertLogs("learningpulse.generator", level="ERROR") as captured:
            result = main(["--count", "1", "--output", str(self.output), "--quarantine", str(self.quarantine)])
        self.assertEqual(result, 1)
        entry = json.loads(JsonLogFormatter().format(captured.records[0]))
        self.assertEqual(entry["status"], "failed")
        self.assertIn("line 1", entry["reason"])
        self.assertFalse(self.quarantine.exists())

    def test_existing_last_line_without_newline(self):
        original = json.dumps(self.records[0]).encode()
        self.output.write_bytes(original)
        self.write([self.records[0]])
        self.assertEqual(self.output.read_bytes(), original)
        self.write(self.records[1:])
        self.assertEqual(self.read_output(), self.records)

    def test_empty_batch_preserves_accepted_output(self):
        self.write(self.records)
        original = self.output.read_bytes()
        count, logs = self.write([])
        self.assertEqual((count, logs[-1]["total"]), (0, 0))
        self.assertEqual(self.output.read_bytes(), original)


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
