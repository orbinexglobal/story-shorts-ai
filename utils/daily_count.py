"""
Daily upload-count tracking for the "exactly 10/day" guarantee.

Source of truth is the YouTube Data API (`count_uploads_today`). But that
needs a token with youtube.readonly scope, and the fallback assumption of 0
would let a run overshoot past the daily target. So we also persist today's
count to a small JSON file that is committed by the workflow after each run.
The file survives across GitHub Actions runs (which are 2h apart), giving a
reliable cap even with an upload-only token.

Write conflicts are not a concern: scheduled runs are sequential.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config.logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_STATE_PATH = Path("state") / "daily_upload_count.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_daily_count(state_path: Path = DEFAULT_STATE_PATH) -> int:
    """Read today's recorded upload count from the state file (0 if missing)."""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    return int(data.get(_today(), 0))


def record_daily_count(count: int, state_path: Path = DEFAULT_STATE_PATH) -> None:
    """Persist today's count, keeping the state file tiny (latest day only)."""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[_today()] = count
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data), encoding="utf-8")
