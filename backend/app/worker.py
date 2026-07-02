from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal, init_db
from app.engine.retry import next_attempt_at
from app.engine.scheduler import schedule_ready_steps
from app.handlers import TransientStepError, execute_step
from app.models import RunStatus, StepStatus, WorkflowRun, WorkflowStep
from app.telemetry import (
    POLL_LATENCY,
    RUNS_COMPLETED,
    STEPS_EXECUTED,
    STEP_DURATION,
    logger,
    setup_telemetry,
    tracer,
    update_pending_gauges,
)


class Worker:
    def __init__(self) -> None:
        self.worker_id = settings.worker_id
        self.lease_seconds = settings.worker_lease_seconds
        self.poll_interval = settings.worker_poll_interval_ms / 1000

    async def run_forever(self) -> None:
        init_db()
        logger.info("worker_started", worker_id=self.worker_id)
        asyncio.create_task(self._reaper_loop())
        while True:
            polled = await self._poll_once()
            if not polled:
                await asyncio.sleep(self.poll_interval)

    async def _reaper_loop(self) -> None:
        while True:
            try:
                self._reap_expired_leases()
            except Exception as exc:
                logger.error("reaper_error", error=str(exc))
            await asyncio.sleep(10)

    def _reap_expired_leases(self) -> None:
        now = datetime.now(UTC)
        with SessionLocal() as session:
            expired = session.scalars(
                select(WorkflowStep).where(
                    WorkflowStep.status == StepStatus.RUNNING.value,
                    WorkflowStep.leased_until < now,
                )
            ).all()
            for step in expired:
                step.status = StepStatus.PENDING.value
                step.leased_until = None
                step.worker_id = None
                logger.warning("lease_reaped", step_id=step.id, run_id=step.run_id)
            session.commit()

    async def _poll_once(self) -> bool:
        start = time.perf_counter()
        step = self._claim_step()
        POLL_LATENCY.observe(time.perf_counter() - start)
        if not step:
            self._update_pending_count()
            return False
        await self._execute(step)
        return True

    def _claim_step(self) -> WorkflowStep | None:
        now = datetime.now(UTC)
        with SessionLocal() as session:
            step = session.scalar(
                select(WorkflowStep)
                .where(
                    WorkflowStep.status == StepStatus.PENDING.value,
                    (WorkflowStep.next_attempt_at.is_(None)) | (WorkflowStep.next_attempt_at <= now),
                )
                .order_by(WorkflowStep.next_attempt_at.nulls_first())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not step:
                session.rollback()
                return None

            if not self._deps_satisfied(session, step):
                session.rollback()
                return None

            run = session.get(WorkflowRun, step.run_id)
            if not run or run.status == RunStatus.CANCELLED.value:
                step.status = StepStatus.SKIPPED.value
                step.completed_at = now
                session.commit()
                return None

            step.status = StepStatus.RUNNING.value
            step.leased_until = now + timedelta(seconds=self.lease_seconds)
            step.worker_id = self.worker_id
            step.started_at = step.started_at or now
            step.attempt += 1
            session.commit()
            session.refresh(step)
            return step

    def _deps_satisfied(self, session, step: WorkflowStep) -> bool:
        deps = step.depends_on or []
        if not deps:
            return True
        completed = session.scalar(
            select(func.count())
            .select_from(WorkflowStep)
            .where(
                WorkflowStep.run_id == step.run_id,
                WorkflowStep.step_key.in_(deps),
                WorkflowStep.status == StepStatus.COMPLETED.value,
            )
        )
        return completed == len(deps)

    async def _execute(self, step: WorkflowStep) -> None:
        with tracer.start_as_current_span("execute_step") as span:
            span.set_attribute("run_id", step.run_id)
            span.set_attribute("step_key", step.step_key)
            span.set_attribute("step_type", step.step_type)
            start = time.perf_counter()
            owner = "unknown"
            try:
                with SessionLocal() as session:
                    run = session.scalar(
                        select(WorkflowRun)
                        .where(WorkflowRun.id == step.run_id)
                        .options(selectinload(WorkflowRun.steps))
                    )
                    db_step = session.get(WorkflowStep, step.id)
                    if not run or not db_step or run.status == RunStatus.CANCELLED.value:
                        return
                    owner = run.submitted_by or "unknown"
                    span.set_attribute("user", owner)
                    from app.engine.scheduler import resolve_step_input

                    db_step.input_data = resolve_step_input(run, db_step)
                    session.commit()
                    input_data = db_step.input_data

                output = await execute_step(step.step_type, step.config or {}, input_data, step.attempt - 1)
                duration = time.perf_counter() - start
                STEP_DURATION.labels(user=owner, step_type=step.step_type).observe(duration)
                STEPS_EXECUTED.labels(user=owner, step_type=step.step_type, status="completed").inc()

                with SessionLocal() as session:
                    db_step = session.get(WorkflowStep, step.id)
                    run = session.get(WorkflowRun, step.run_id)
                    if not db_step or not run:
                        return
                    db_step.status = StepStatus.COMPLETED.value
                    db_step.output = output
                    db_step.completed_at = datetime.now(UTC)
                    db_step.leased_until = None
                    db_step.error = None
                    schedule_ready_steps(session, run.id)
                    if run.status == RunStatus.COMPLETED.value:
                        RUNS_COMPLETED.labels(user=owner, status="completed").inc()
                    session.commit()
                logger.info("step_completed", run_id=step.run_id, step_key=step.step_key, duration=duration)
            except TransientStepError as exc:
                STEPS_EXECUTED.labels(user=owner, step_type=step.step_type, status="retried").inc()
                self._schedule_retry(step, str(exc))
            except Exception as exc:
                STEPS_EXECUTED.labels(user=owner, step_type=step.step_type, status="failed").inc()
                self._fail_step(step, str(exc), owner=owner)

    def _schedule_retry(self, step: WorkflowStep, error: str) -> None:
        with SessionLocal() as session:
            db_step = session.get(WorkflowStep, step.id)
            if not db_step:
                return
            if db_step.attempt >= db_step.max_attempts:
                self._fail_step(step, error, session=session)
                return
            db_step.status = StepStatus.PENDING.value
            db_step.next_attempt_at = next_attempt_at(db_step.attempt)
            db_step.leased_until = None
            db_step.worker_id = None
            db_step.error = error
            session.commit()
        logger.warning("step_retry", run_id=step.run_id, step_key=step.step_key, error=error)

    def _fail_step(self, step: WorkflowStep, error: str, session=None, owner: str = "unknown") -> None:
        close = False
        if session is None:
            session = SessionLocal()
            close = True
        try:
            db_step = session.get(WorkflowStep, step.id)
            run = session.get(WorkflowRun, step.run_id)
            if not db_step or not run:
                return
            owner = run.submitted_by or owner
            db_step.status = StepStatus.FAILED.value
            db_step.error = error
            db_step.completed_at = datetime.now(UTC)
            db_step.leased_until = None
            run.status = RunStatus.FAILED.value
            RUNS_COMPLETED.labels(user=owner, status="failed").inc()
            session.commit()
            logger.error("step_failed", run_id=step.run_id, step_key=step.step_key, error=error)
        finally:
            if close:
                session.close()

    def _update_pending_count(self) -> None:
        with SessionLocal() as session:
            rows = session.execute(
                select(WorkflowRun.submitted_by, func.count())
                .join(WorkflowStep, WorkflowStep.run_id == WorkflowRun.id)
                .where(WorkflowStep.status == StepStatus.PENDING.value)
                .group_by(WorkflowRun.submitted_by)
            ).all()
            update_pending_gauges({user: count for user, count in rows})


async def main() -> None:
    setup_telemetry("workflow-worker")
    if settings.worker_metrics_port:
        from app.telemetry import start_worker_metrics_server

        start_worker_metrics_server(settings.worker_metrics_port)
    worker = Worker()
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
