# LearningPulse — Architecture Direction

## Purpose

LearningPulse is a synthetic reference platform for exploring production-oriented data engineering and data architecture patterns. The architecture will be implemented incrementally across the 13-week plan rather than as disconnected tutorial exercises.

## Planned end-to-end flow

```text
Synthetic Python Event Generator
            |
            v
          Kafka
            |
            v
           Spark
       /           \
   Batch         Streaming
       \           /
        v         v
      Bronze -> Silver -> Gold
                 |
                 v
              Iceberg
                 |
                 v
       Analytics-ready outputs

Cross-cutting concerns:
- Data quality and contracts
- Observability and SLOs
- Lineage and governance
- Security and access control
- Infrastructure as Code
- CI/CD
- Cost and reliability trade-offs
```

## Planned components

### 1. Synthetic Python event generator
Creates realistic but fully synthetic learning, assessment, and engagement events. It will later support deterministic generation, validation, error cases, and batch/streaming output.

### 2. Kafka
Provides the event-streaming layer. Later milestones will cover message keys, partitions, consumer groups, offsets, replay, delivery semantics, and failure handling.

### 3. Spark
Provides distributed processing for both batch and streaming workloads. Later milestones will cover explicit schemas, transformations, joins, aggregations, performance tuning, checkpoints, watermarking, and deduplication.

### 4. Bronze / Silver / Gold data layers
- **Bronze:** minimally transformed ingested events plus ingestion metadata.
- **Silver:** validated, standardized, deduplicated, and enriched records.
- **Gold:** analytics-ready aggregates and domain-oriented outputs.

### 5. Iceberg
Provides a lakehouse table layer for schema evolution, snapshots, upserts, partition evolution, and table maintenance.

### 6. Observability and governance
Later milestones will add measurable quality controls, operational metrics, SLOs, lineage metadata, data classification, access design, runbooks, and architecture decision records.

## Initial constraints

1. Synthetic data only.
2. Local-first and low-cost.
3. Reproducible setup.

## Architecture status

**Milestone 1: Scaffold only.** No Kafka, Spark, Iceberg, or cloud infrastructure is implemented yet by design.
