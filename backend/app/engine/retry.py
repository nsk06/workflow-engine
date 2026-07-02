from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

MAX_BACKOFF_SECONDS = 60


def compute_backoff(attempt: int) -> float:
    base = min(MAX_BACKOFF_SECONDS, 2**attempt)
    return base + random.uniform(0, 1)


def next_attempt_at(attempt: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=compute_backoff(attempt))
