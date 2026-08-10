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

## Current milestone — Project Scaffold

This first milestone intentionally contains only the project foundation. Kafka, Spark, Iceberg, pipelines, and infrastructure implementation are **not** part of this milestone.

### Completion criteria

- Repository structure exists.
- Problem and scope are documented.
- Initial architecture direction is documented.
- Three project constraints are recorded.
- Initial Git commit is created.
