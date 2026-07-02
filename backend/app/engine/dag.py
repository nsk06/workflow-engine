from __future__ import annotations

from app.schemas import StepDefinition, WorkflowDefinition

MAX_STEPS = 10
ALLOWED_TYPES = {"sleep", "flaky", "transform"}


class DagValidationError(ValueError):
    pass


def validate_workflow(defn: WorkflowDefinition) -> None:
    if not defn.steps:
        raise DagValidationError("Workflow must have at least one step")
    if len(defn.steps) > MAX_STEPS:
        raise DagValidationError(f"Workflow exceeds max {MAX_STEPS} steps")

    keys = [s.key for s in defn.steps]
    if len(keys) != len(set(keys)):
        raise DagValidationError("Duplicate step keys")

    key_set = set(keys)
    for step in defn.steps:
        if step.type not in ALLOWED_TYPES:
            raise DagValidationError(f"Unknown step type: {step.type}")
        for dep in step.depends_on:
            if dep not in key_set:
                raise DagValidationError(f"Step {step.key} depends on unknown step {dep}")
            if dep == step.key:
                raise DagValidationError(f"Step {step.key} cannot depend on itself")

    _assert_acyclic(defn.steps)


def _assert_acyclic(steps: list[StepDefinition]) -> None:
    graph = {s.key: s.depends_on for s in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise DagValidationError("Workflow contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for key in graph:
        visit(key)


def topological_order(steps: list[StepDefinition]) -> list[str]:
    validate_workflow(WorkflowDefinition(name="tmp", steps=steps))
    graph = {s.key: s.depends_on for s in steps}
    result: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        for dep in graph[node]:
            visit(dep)
        visited.add(node)
        result.append(node)

    for key in graph:
        visit(key)
    return result


def root_steps(steps: list[StepDefinition]) -> list[str]:
    return [s.key for s in steps if not s.depends_on]
