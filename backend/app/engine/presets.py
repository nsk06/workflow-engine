from __future__ import annotations

from app.schemas import StepDefinition, WorkflowDefinition

PRESETS: dict[str, WorkflowDefinition] = {
    "linear": WorkflowDefinition(
        name="linear-pipeline",
        steps=[
            StepDefinition(key="validate", type="transform", config={"op": "validate"}),
            StepDefinition(key="enrich", type="transform", depends_on=["validate"], config={"op": "enrich"}),
            StepDefinition(key="process", type="sleep", depends_on=["enrich"], config={"duration_ms": 300}),
            StepDefinition(key="finalize", type="transform", depends_on=["process"], config={"op": "finalize"}),
        ],
    ),
    "fanout": WorkflowDefinition(
        name="fanout-fanin",
        steps=[
            StepDefinition(key="validate", type="transform", config={"op": "validate"}),
            StepDefinition(key="branch_a", type="sleep", depends_on=["validate"], config={"duration_ms": 400}),
            StepDefinition(key="branch_b", type="sleep", depends_on=["validate"], config={"duration_ms": 500}),
            StepDefinition(key="aggregate", type="transform", depends_on=["branch_a", "branch_b"], config={"op": "aggregate"}),
            StepDefinition(key="finalize", type="transform", depends_on=["aggregate"], config={"op": "finalize"}),
        ],
    ),
    "flaky": WorkflowDefinition(
        name="flaky-chain",
        steps=[
            StepDefinition(key="start", type="transform", config={"op": "validate"}),
            StepDefinition(
                key="flaky_check",
                type="flaky",
                depends_on=["start"],
                config={"failures_before_success": 2, "duration_ms": 150},
            ),
            StepDefinition(key="finalize", type="sleep", depends_on=["flaky_check"], config={"duration_ms": 200}),
        ],
    ),
}


def get_preset(name: str) -> WorkflowDefinition:
    if name not in PRESETS:
        raise ValueError(f"Unknown preset: {name}. Available: {', '.join(PRESETS)}")
    return PRESETS[name].model_copy(deep=True)
