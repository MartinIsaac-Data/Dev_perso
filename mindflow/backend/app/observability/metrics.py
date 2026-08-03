"""Prometheus metrics (Architecture.md §12.4)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

# -- Technical (RED) --------------------------------------------------------
http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "route", "status"],
    registry=REGISTRY,
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)
job_duration_seconds = Histogram(
    "job_duration_seconds",
    "Pipeline job latency",
    ["job", "result"],
    buckets=(0.5, 1, 2.5, 5, 10, 20, 40, 80, 160, 320),
    registry=REGISTRY,
)
job_retries_total = Counter(
    "job_retries_total", "Job retries", ["job", "reason"], registry=REGISTRY
)
queue_depth = Gauge("queue_depth", "Pending jobs", ["queue"], registry=REGISTRY)

# -- AI ---------------------------------------------------------------------
llm_tokens_total = Counter(
    "llm_tokens_total", "Tokens consumed", ["model", "operation", "kind"], registry=REGISTRY
)
llm_cost_micro_eur_total = Counter(
    "llm_cost_micro_eur_total", "AI cost in micro-euros", ["model", "operation"], registry=REGISTRY
)
stt_duration_seconds = Histogram(
    "stt_duration_seconds",
    "Transcription latency",
    ["engine"],
    buckets=(0.5, 1, 2, 5, 10, 20, 60, 180),
    registry=REGISTRY,
)

# -- Product ----------------------------------------------------------------
captures_created_total = Counter(
    "captures_created_total", "Captures created", ["source"], registry=REGISTRY
)
capture_time_to_publish_seconds = Histogram(
    "capture_time_to_publish_seconds",
    "Delay between upload completion and publication",
    buckets=(2, 5, 10, 15, 25, 40, 60, 120, 300),
    registry=REGISTRY,
)
entries_created_total = Counter(
    "entries_created_total", "Entries created", ["entry_type", "origin"], registry=REGISTRY
)
entries_corrected_total = Counter(
    "entries_corrected_total", "User corrections", ["field"], registry=REGISTRY
)

# -- Planning and delivery (Phase 2) ----------------------------------------
entries_completed_total = Counter(
    "entries_completed_total", "Entries completed", ["entry_type"], registry=REGISTRY
)
tasks_recurred_total = Counter(
    "tasks_recurred_total", "Recurring occurrences generated", registry=REGISTRY
)
reminders_scheduled_total = Counter(
    "reminders_scheduled_total", "Reminders scheduled", ["channel"], registry=REGISTRY
)
reminders_delivered_total = Counter(
    "reminders_delivered_total", "Reminder deliveries", ["provider", "result"], registry=REGISTRY
)
# How late a reminder actually fired. A reminder that arrives after the moment
# it was meant to prevent is worse than none, so this is the SLI that matters
# for the whole notification plane.
reminder_delivery_lag_seconds = Histogram(
    "reminder_delivery_lag_seconds",
    "Delay between the scheduled time and the actual send",
    buckets=(1, 5, 15, 30, 60, 120, 300, 900),
    registry=REGISTRY,
)
search_queries_total = Counter(
    "search_queries_total", "Search queries", ["mode", "outcome"], registry=REGISTRY
)
search_duration_seconds = Histogram(
    "search_duration_seconds",
    "Search latency",
    ["mode"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=REGISTRY,
)

# The one metric that must always read zero (Architecture.md §12.7).
captures_lost_total = Counter(
    "captures_lost_total", "Captures irrecoverably lost", ["stage"], registry=REGISTRY
)

# -- AI layer (Phase 3) ------------------------------------------------------
chunks_indexed_total = Counter(
    "chunks_indexed_total", "Chunks written to the index", ["source"], registry=REGISTRY
)
chunks_embedded_total = Counter(
    "chunks_embedded_total", "Chunks embedded", ["provider", "outcome"], registry=REGISTRY
)
# The backlog. A number that climbs and never falls means the embedding worker
# has stopped, and semantic search is quietly answering from a stale corpus —
# which looks identical to answering correctly.
embedding_backlog = Gauge("embedding_backlog", "Chunks awaiting an embedding", registry=REGISTRY)
assistant_questions_total = Counter(
    "assistant_questions_total", "Assistant questions", ["intent", "outcome"], registry=REGISTRY
)
assistant_duration_seconds = Histogram(
    "assistant_duration_seconds",
    "Time to a complete assistant answer",
    ["intent"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0),
    registry=REGISTRY,
)
# Answers generated with no supporting passage. Every one of them is a sentence
# the system cannot back, so this is the honesty metric.
assistant_uncited_answers_total = Counter(
    "assistant_uncited_answers_total", "Answers produced with no citation", registry=REGISTRY
)
entities_extracted_total = Counter(
    "entities_extracted_total", "Entities extracted", ["kind"], registry=REGISTRY
)
digests_generated_total = Counter(
    "digests_generated_total", "Digests generated", ["period", "outcome"], registry=REGISTRY
)
