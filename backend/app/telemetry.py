from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest, start_http_server

from app.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

RUNS_SUBMITTED = Counter("workflow_runs_submitted_total", "Workflow runs submitted", ["user"])
RUNS_COMPLETED = Counter("workflow_runs_completed_total", "Workflow runs completed", ["user", "status"])
STEPS_EXECUTED = Counter(
    "workflow_steps_executed_total", "Steps executed", ["user", "step_type", "status"]
)
STEP_DURATION = Histogram(
    "workflow_step_duration_seconds", "Step execution duration", ["user", "step_type"]
)
PENDING_STEPS = Gauge("workflow_pending_steps", "Pending workflow steps", ["user"])
POLL_LATENCY = Histogram("workflow_worker_poll_latency_seconds", "Worker poll latency")

logger = structlog.get_logger()
tracer = trace.get_tracer("workflow-engine")


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


def setup_telemetry(service_name: str) -> None:
    setup_logging()
    if not settings.otel_enabled:
        return
    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception as exc:
        logger.warning("otel_setup_failed", error=str(exc))


def mount_metrics(app: FastAPI) -> None:
    from fastapi import Response

    @app.get("/metrics")
    def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def update_pending_gauges(counts_by_user: dict[str, int]) -> None:
    for user, count in counts_by_user.items():
        PENDING_STEPS.labels(user=user).set(count)


def start_worker_metrics_server(port: int) -> None:
    start_http_server(port)
