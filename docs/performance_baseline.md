# LearningPulse performance baseline

Measured on 2026-10-22 with 100,000 generated events and random seed `42`.
These results describe the local working-tree implementation with validation,
quarantine routing, and first-accepted-record duplicate handling. The duplicate
handling changes were not committed when these measurements were taken.

## Machine and execution assumptions

- OS: macOS 12.7.6, build 21H1320; architecture: x86_64.
- Interpreter: Python 3.13.15, invoked through `python3.13`.
- CPU model, logical core count, and RAM: unavailable from the sandbox;
  hardware queries were denied. Storage model and free memory were not measured.
- Execution: one local CLI process and one writer, using local filesystem output.
  No concurrent writers, Kafka, Spark, or network services were involved.
- Background machine load and filesystem cache state were not controlled.
  These are individual observations, not a sustained-load or statistical benchmark.
- Fresh runs used separate, initially empty output directories. Replay reused
  the second run's accepted output and quarantine paths.
- Timing used `time.perf_counter()` around the CLI subprocess. It includes process
  startup, generation, validation, duplicate checks, logging, file writes, and
  normal file close. Verification afterward is excluded. No explicit `fsync`
  was performed, so this does not measure durable-storage flush latency.
- Throughput is input events processed divided by elapsed seconds, including
  skipped duplicates on replay. IDs are retained in memory for deduplication;
  peak memory was not measured.

## Results

| Run | Elapsed seconds | Events/sec | Accepted output bytes | Output MiB | Valid accepted | Invalid | Duplicates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial fresh run | 5.307112 | 18,842.64 | 34,184,678 | 32.601 | 100,000 | 0 | 0 |
| Fresh repeat, same seed | 5.286027 | 18,917.80 | 34,184,678 | 32.601 | 100,000 | 0 | 0 |
| Replay into existing output | 10.489581 | 9,533.27 | 34,184,678 | 32.601 | 0 | 0 | 100,000 |

MiB means bytes divided by 1,048,576. Counts are per invocation; output size is
the resulting accepted file size, not the number of bytes newly appended.
The quarantine file remained empty in all runs.

Replay includes scanning and validating the existing 100,000 accepted records,
plus logging 100,000 duplicate messages. Its workload therefore differs from a
fresh run; the timings alone do not isolate the cost of each operation.

## Verification

- Every invocation completed successfully. Repeat and replay explicitly returned
  exit code 0, contained no warning/error/critical log records, and emitted one
  completion summary each.
- Summary counts reconciled: accepted + rejected + duplicates = 100,000.
  Accepted and quarantine file line counts matched their summaries.
- Both fresh runs produced 100,000 unique accepted IDs. All non-timestamp fields
  matched record-for-record between fresh runs.
- The seed fixes random choices, not the reference clock. Timestamps differ
  between fresh runs because `generated_at` defaults to the current time.
- Replay logged exactly 100,000 duplicate entries with reasons, covering every
  accepted ID. SHA-256 comparison confirmed the accepted output was unchanged.
- These checks found no silent failures in the measured runs. They do not test
  concurrent writers, interrupted writes, or filesystem failures.

## Reproduction and evidence

From the project root, select a new directory for each fresh run:

```bash
PYTHONPATH=src python3.13 -m learningpulse.generator \
  --count 100000 --seed 42 \
  --output data/raw/benchmarks/NEW_RUN/events.jsonl \
  --quarantine data/raw/benchmarks/NEW_RUN/invalid_events.jsonl \
  2> data/raw/benchmarks/NEW_RUN/run.log
```

Create `NEW_RUN` before running the command because the shell opens the log file
first. Replace `NEW_RUN` with a fresh directory name; use the same paths for a
replay and a separate log filename to preserve the first run's logs. The command
generates data; an external timer around its subprocess is required to reproduce
the elapsed-time measurement described above.

Detailed local evidence (generated artifacts are ignored by Git):

- `data/raw/benchmarks/events-100000-yjatajj3/results.json`
- `data/raw/benchmarks/events-100000-yjatajj3/run.log`
- `data/raw/benchmarks/repeat-100000-gil2bo5m/verification.json`
- `data/raw/benchmarks/repeat-100000-gil2bo5m/fresh.log`
- `data/raw/benchmarks/repeat-100000-gil2bo5m/replay.log`

Accepted events and empty quarantine files are retained alongside these reports.
