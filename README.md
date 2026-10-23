# LearningPulse

LearningPulse is a **synthetic, production-style portfolio project** for designing and implementing a near-real-time learning and assessment analytics platform.

## Problem statement

Learning and assessment platforms generate events such as assessment attempts, scores, completions, and engagement activity. A realistic data platform must ingest those events reliably, support both batch and streaming processing, enforce data quality, and produce analytics-ready outputs for downstream reporting and analysis.

LearningPulse will evolve over the 13-week career plan to demonstrate those concerns with **synthetic data only**.

## Project goal

Build an end-to-end reference platform that can eventually:

1. Generate synthetic assessment and engagement events.
2. Ingest batch and streaming data.
3. Process events through Bronze, Silver, and Gold layers.
4. Support event streaming with Kafka.
5. Use Spark for distributed batch and streaming transformations.
6. Store analytics-ready data in a lakehouse-style layout using Iceberg.
7. Add data-quality controls, observability, lineage, governance, and security design.
8. Define an AWS-oriented infrastructure design with Terraform without requiring unnecessary cloud spend.
9. Document architectural decisions, trade-offs, failure modes, and operational practices.

## Initial repository structure

```text
learningpulse/
├── src/
│   └── learningpulse/
├── tests/
├── data/
│   ├── raw/
│   └── quarantine/
├── docs/
│   ├── adr/
│   └── architecture.md
├── infra/
├── docker/
├── pyproject.toml
├── .gitignore
└── README.md
```

## Project constraints

1. **Synthetic data only** — no employer, customer, student, healthcare, or other real confidential data will be used.
2. **Local-first and low-cost** — implementations should run locally wherever practical; paid cloud resources are optional and must not be required to understand the architecture.
3. **Reproducible setup** — another engineer should be able to understand the repository structure, environment assumptions, and execution steps from the documentation.

## Current milestone — Validated generator, configuration, and quarantine

The project includes a versioned JSON Schema contract, a typed Python generator,
record validation, external configuration, and structured failure logging.
Kafka and Spark remain outside this milestone.

### Generate the data

From the repository root, run:

```bash
python -m learningpulse.generator --count 1000 --seed 42
```

When the package is not installed, set the source path explicitly:

```bash
PYTHONPATH=src python -m learningpulse.generator --count 1000 --seed 42
```

The generator writes newline-delimited JSON to
`data/raw/assessment_events/date=YYYY-MM-DD/events.jsonl`. Use `--output` to
choose another location. Supplying `--seed` makes generated identifiers,
subjects, scores, and relative event timing reproducible; timestamps are anchored
to the time the command starts.

### Configuration and validation

Run commands from the repository root. Relative output paths are resolved against
the current working directory. Configuration lives in `src/learningpulse/config.py`;
explicit CLI options override environment values, which override defaults.

| CLI option | Environment variable | Default |
| --- | --- | --- |
| `--count` / `--record-count` | `LEARNINGPULSE_RECORD_COUNT` | `1000` |
| `--output` | `LEARNINGPULSE_OUTPUT_PATH` | Date-partitioned path above |
| `--quarantine` | `LEARNINGPULSE_QUARANTINE_PATH` | `data/quarantine/invalid_events.jsonl` |
| `--seed` | `LEARNINGPULSE_SEED` | Unseeded |

For example:

```bash
LEARNINGPULSE_RECORD_COUNT=1000 LEARNINGPULSE_OUTPUT_PATH=data/raw/example.jsonl \
  PYTHONPATH=src python -m learningpulse.generator --seed 42
```

`validation.py` checks required UUID IDs, timezone-aware ISO 8601 timestamps,
ingestion not preceding completion, the assessment event type, allowed subjects,
integer scores, `score >= 0`, `max_score > 0`, and `score <= max_score`.
It returns all rejection reasons instead of raising for invalid field values.

`write_jsonl()` validates each event before writing. Existing accepted output is
preserved, and only new valid `event_id` values are appended. The first accepted
record wins: later valid records with the same exact ID string are skipped, even
if their other fields differ. This applies within a batch and across sequential
runs targeting the same output file. Duplicates are logged with
`status="duplicate"` and a reason; they do not go to quarantine.

Invalid records are appended to quarantine as JSON objects containing
`record`, `status`, and `reasons`; processing continues with the next event.
JSON logs go to stderr and include `event_id`, `status`, and `reason`. A final
summary includes `accepted`, `rejected`, `duplicates`, and `total` for the current
batch, where `total = accepted + rejected + duplicates`. The `accepted` count and
the writer's return value count only newly appended records. Invalid records do
not reserve an ID, so a later valid record with that ID can still be accepted.
The quarantine file can contain rejected records from multiple runs.

Invalid configuration stops before generation. Filesystem errors are logged and
produce exit code 1, since the run cannot safely continue without writable output.
Batch output is not transactional: a filesystem failure can leave partial files.
Before writing, the writer validates existing accepted output and loads its IDs
into an in-memory set. Malformed records or existing duplicate IDs cause the CLI
to log an error and exit with code 1 without modifying either output file.
Repair such files explicitly before retrying. This implementation assumes one
writer at a time; concurrent writes and crash recovery are not supported. Memory
usage grows with the number of unique accepted IDs in the output file.

### Verify valid and invalid records

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The mixed-batch test generates six events and deliberately corrupts three:
a negative score, a missing learner ID, and an invalid timestamp. It verifies
three accepted records, three quarantined records with reasons, structured
failure logs, and continued processing after rejection. Other checks cover 1,000
valid generated records, boundary scores, malformed fields, and configuration precedence.

Duplicate tests replay the same three-record input twice: the first run accepts
three records, and the second accepts zero and reports three duplicates. The
accepted output remains byte-for-byte unchanged with one record per ID. Tests
also cover overlapping batches, changed payloads with reused IDs, invalid records
followed by valid records with the same ID, and malformed existing output.

### Assessment event v1 fields

The machine-readable contract is
[`contracts/assessment_event_v1.json`](contracts/assessment_event_v1.json).

| Field | Meaning |
| --- | --- |
| `event_id` | UUID uniquely identifying this emitted event. |
| `learner_id` | Synthetic UUID identifying the learner. |
| `assessment_id` | Synthetic UUID identifying the assessment. |
| `subject` | Assessment subject from the contract's allowed values. |
| `score` | Integer points earned, always from zero through `max_score`. |
| `max_score` | Maximum points available for the assessment. |
| `event_type` | Event discriminator; v1 emits `assessment_completed`. |
| `occurred_at` | Time the learner completed the assessment, as an ISO 8601 timestamp. |
| `ingested_at` | Time the platform received the event, one to 180 seconds later. |

### Completion criteria

- Versioned assessment-event contract exists.
- Generator creates 1,000 valid-looking synthetic records by default.
- JSONL output is stored in a date-partitioned raw-data folder.
- Every event field is documented.
- Invalid records are rejected with reasons and appended to quarantine.
- Valid records continue processing after rejection.
- Record count and paths are configurable outside generation logic.
- Structured logs identify failures and summarize accepted/rejected counts.
