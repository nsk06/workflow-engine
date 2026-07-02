from __future__ import annotations

from pydantic import BaseModel, Field


class StepDefinition(BaseModel):
    key: str
    type: str
    depends_on: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    name: str = "workflow"
    input: dict = Field(default_factory=dict)
    steps: list[StepDefinition]


class SubmitRunRequest(BaseModel):
    name: str | None = None
    preset: str | None = None
    definition: WorkflowDefinition | None = None
    input: dict = Field(default_factory=dict)


class SubmitRunResponse(BaseModel):
    run_id: str
    status: str


class StepResponse(BaseModel):
    id: str
    step_key: str
    status: str
    step_type: str
    depends_on: list[str]
    config: dict
    input: dict
    output: dict | None
    attempt: int
    error: str | None
    started_at: str | None
    completed_at: str | None

    model_config = {"from_attributes": True}


class RunSummary(BaseModel):
    id: str
    name: str
    status: str
    submitted_by: str
    created_at: str
    updated_at: str
    step_counts: dict[str, int]

    model_config = {"from_attributes": True}


class RunDetail(BaseModel):
    id: str
    name: str
    status: str
    submitted_by: str
    input: dict
    output: dict | None
    definition: dict
    created_at: str
    updated_at: str
    cancelled_at: str | None
    steps: list[StepResponse]
