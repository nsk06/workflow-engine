import pytest

from app.engine.dag import DagValidationError, validate_workflow, root_steps
from app.engine.retry import compute_backoff
from app.schemas import StepDefinition, WorkflowDefinition


def test_validate_linear_dag():
    defn = WorkflowDefinition(
        name="test",
        steps=[
            StepDefinition(key="a", type="sleep"),
            StepDefinition(key="b", type="transform", depends_on=["a"]),
        ],
    )
    validate_workflow(defn)
    assert root_steps(defn.steps) == ["a"]


def test_reject_cycle():
    defn = WorkflowDefinition(
        name="test",
        steps=[
            StepDefinition(key="a", type="sleep", depends_on=["b"]),
            StepDefinition(key="b", type="sleep", depends_on=["a"]),
        ],
    )
    with pytest.raises(DagValidationError, match="cycle"):
        validate_workflow(defn)


def test_reject_too_many_steps():
    steps = [StepDefinition(key=f"s{i}", type="sleep") for i in range(11)]
    with pytest.raises(DagValidationError):
        validate_workflow(WorkflowDefinition(name="big", steps=steps))


def test_backoff_grows():
    assert compute_backoff(1) < compute_backoff(4)
