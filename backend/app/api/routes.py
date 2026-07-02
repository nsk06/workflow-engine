from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import User, get_current_user
from app.db import get_db
from app.engine.dag import DagValidationError, root_steps, validate_workflow
from app.engine.presets import get_preset
from app.engine.scheduler import mark_run_cancelled, schedule_ready_steps
from app.models import RunStatus, StepStatus, WorkflowRun, WorkflowStep
from app.schemas import RunDetail, RunSummary, StepResponse, SubmitRunRequest, SubmitRunResponse
from app.telemetry import RUNS_SUBMITTED, logger, tracer

router = APIRouter(prefix="/runs", tags=["runs"])


def _step_response(step: WorkflowStep) -> StepResponse:
    return StepResponse(
        id=step.id,
        step_key=step.step_key,
        status=step.status,
        step_type=step.step_type,
        depends_on=step.depends_on or [],
        config=step.config or {},
        input=step.input_data or {},
        output=step.output,
        attempt=step.attempt,
        error=step.error,
        started_at=step.started_at.isoformat() if step.started_at else None,
        completed_at=step.completed_at.isoformat() if step.completed_at else None,
    )


def _get_owned_run(db: Session, run_id: str, user: User) -> WorkflowRun:
    run = db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.submitted_by == user.sub)
        .options(selectinload(WorkflowRun.steps))
    )
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("", response_model=list[RunSummary])
def list_runs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 50,
):
    runs = db.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.submitted_by == user.sub)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    ).all()
    summaries = []
    for run in runs:
        counts = dict(
            db.execute(
                select(WorkflowStep.status, func.count())
                .where(WorkflowStep.run_id == run.id)
                .group_by(WorkflowStep.status)
            ).all()
        )
        summaries.append(
            RunSummary(
                id=run.id,
                name=run.name,
                status=run.status,
                submitted_by=run.submitted_by,
                created_at=run.created_at.isoformat() if run.created_at else "",
                updated_at=run.updated_at.isoformat() if run.updated_at else "",
                step_counts=counts,
            )
        )
    return summaries


@router.post("", response_model=SubmitRunResponse, status_code=202)
def submit_run(
    body: SubmitRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    with tracer.start_as_current_span("submit_run") as span:
        span.set_attribute("user", user.sub)
        if body.preset:
            definition = get_preset(body.preset)
        elif body.definition:
            definition = body.definition
        else:
            raise HTTPException(400, "Provide preset or definition")

        if body.name:
            definition.name = body.name
        if body.input:
            definition.input = body.input

        try:
            validate_workflow(definition)
        except (DagValidationError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

        run = WorkflowRun(
            name=definition.name,
            definition=definition.model_dump(),
            input=definition.input,
            status=RunStatus.PENDING.value,
            submitted_by=user.sub,
        )
        db.add(run)
        db.flush()

        roots = set(root_steps(definition.steps))
        for step_def in definition.steps:
            step = WorkflowStep(
                run_id=run.id,
                step_key=step_def.key,
                step_type=step_def.type,
                config=step_def.config,
                depends_on=step_def.depends_on,
                status=StepStatus.PENDING.value if step_def.key in roots else StepStatus.PENDING.value,
            )
            db.add(step)

        db.flush()
        schedule_ready_steps(db, run.id)
        RUNS_SUBMITTED.labels(user=user.sub).inc()
        logger.info("run_submitted", run_id=run.id, name=run.name, user=user.sub)
        return SubmitRunResponse(run_id=run.id, status=run.status)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = _get_owned_run(db, run_id, user)
    steps = sorted(run.steps, key=lambda s: s.step_key)
    return RunDetail(
        id=run.id,
        name=run.name,
        status=run.status,
        submitted_by=run.submitted_by,
        input=run.input or {},
        output=run.output,
        definition=run.definition or {},
        created_at=run.created_at.isoformat() if run.created_at else "",
        updated_at=run.updated_at.isoformat() if run.updated_at else "",
        cancelled_at=run.cancelled_at.isoformat() if run.cancelled_at else None,
        steps=[_step_response(s) for s in steps],
    )


@router.get("/{run_id}/steps", response_model=list[StepResponse])
def get_run_steps(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = _get_owned_run(db, run_id, user)
    return [_step_response(s) for s in sorted(run.steps, key=lambda s: s.step_key)]


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = _get_owned_run(db, run_id, user)
    if run.status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value):
        raise HTTPException(400, f"Cannot cancel run in status {run.status}")
    mark_run_cancelled(db, run)
    logger.info("run_cancelled", run_id=run_id, user=user.sub)
    return {"run_id": run_id, "status": RunStatus.CANCELLED.value}


presets_router = APIRouter(prefix="/presets", tags=["presets"])


@presets_router.get("")
def list_presets(user: User = Depends(get_current_user)):
    from app.engine.presets import PRESETS

    return [{"id": k, "name": v.name, "steps": len(v.steps)} for k, v in PRESETS.items()]
