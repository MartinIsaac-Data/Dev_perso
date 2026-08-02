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

# The one metric that must always read zero (Architecture.md §12.7).
captures_lost_total = Counter(
    "captures_lost_total", "Captures irrecoverably lost", ["stage"], registry=REGISTRY
)
