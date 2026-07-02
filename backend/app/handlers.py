import asyncio
import random
import time
from typing import Any


class TransientStepError(Exception):
    pass


async def execute_step(step_type: str, config: dict, input_data: dict, attempt: int) -> dict[str, Any]:
    if step_type == "sleep":
        return await _sleep(config)
    if step_type == "flaky":
        return await _flaky(config, attempt)
    if step_type == "transform":
        return _transform(config, input_data)
    raise ValueError(f"Unknown step type: {step_type}")


async def _sleep(config: dict) -> dict[str, Any]:
    duration_ms = int(config.get("duration_ms", 200))
    await asyncio.sleep(duration_ms / 1000)
    return {"slept_ms": duration_ms}


async def _flaky(config: dict, attempt: int) -> dict[str, Any]:
    failures = int(config.get("failures_before_success", 2))
    duration_ms = int(config.get("duration_ms", 100))
    await asyncio.sleep(duration_ms / 1000)
    if attempt < failures:
        if random.random() < 0.85:
            raise TransientStepError(f"Simulated transient failure (attempt {attempt + 1})")
    return {"flaky": True, "attempts": attempt + 1}


def _transform(config: dict, input_data: dict) -> dict[str, Any]:
    op = config.get("op", "pass")
    upstream = input_data.get("upstream", {})
    return {"op": op, "upstream_keys": list(upstream.keys()), "result": f"{op}_ok"}
