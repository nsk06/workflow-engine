from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RunStatus, StepStatus, WorkflowRun, WorkflowStep


def resolve_step_input(run: WorkflowRun, step: WorkflowStep) -> dict:
    resolved = {"run_input": run.input, "upstream": {}}
    steps_by_key = {s.step_key: s for s in run.steps}
    for dep in step.depends_on:
        dep_step = steps_by_key.get(dep)
        if dep_step and dep_step.output:
            resolved["upstream"][dep] = dep_step.output
    return resolved


def schedule_ready_steps(session: Session, run_id: str) -> int:
    run = session.get(WorkflowRun, run_id)
    if not run or run.status in (RunStatus.CANCELLED.value, RunStatus.FAILED.value):
        return 0

    steps = session.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run_id)).all()
    by_key = {s.step_key: s for s in steps}
    completed = {s.step_key for s in steps if s.status == StepStatus.COMPLETED.value}
    scheduled = 0

    for step in steps:
        if step.status != StepStatus.PENDING.value:
            continue
        if not all(dep in completed for dep in step.depends_on):
            continue
        step.input_data = resolve_step_input(run, step)
        scheduled += 1

    if run.status == RunStatus.PENDING.value:
        run.status = RunStatus.RUNNING.value

    _refresh_run_status(session, run, steps)
    return scheduled


def _refresh_run_status(session: Session, run: WorkflowRun, steps: list[WorkflowStep]) -> None:
    if run.status == RunStatus.CANCELLED.value:
        return

    statuses = {s.status for s in steps}
    if StepStatus.FAILED.value in statuses:
        run.status = RunStatus.FAILED.value
        run.updated_at = datetime.now(UTC)
        return

    terminal = {
        StepStatus.COMPLETED.value,
        StepStatus.SKIPPED.value,
        StepStatus.CANCELLED.value,
    }
    if all(s.status in terminal for s in steps):
        run.status = RunStatus.COMPLETED.value
        outputs = {s.step_key: s.output for s in steps if s.output}
        run.output = {"steps": outputs}
        run.updated_at = datetime.now(UTC)


def mark_run_cancelled(session: Session, run: WorkflowRun) -> None:
    run.status = RunStatus.CANCELLED.value
    run.cancelled_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    steps = session.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run.id)).all()
    for step in steps:
        if step.status in (StepStatus.PENDING.value, StepStatus.RUNNING.value):
            step.status = StepStatus.CANCELLED.value
            step.completed_at = datetime.now(UTC)
