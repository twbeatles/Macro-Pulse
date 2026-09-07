from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


DEFAULT_LOOKBACK_HOURS = 6
ACTIVE_STATUSES = frozenset({"in_progress", "queued", "waiting", "pending", "requested"})


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def should_skip_duplicate_delivery(
    workflow_runs: Sequence[Mapping[str, Any]],
    current_run_id: int,
    now: datetime,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
) -> bool:
    """Skip if another successful or still-running scheduled run exists in lookback.

    GitHub often delays cron jobs by hours. A fixed UTC clock window (for example
    06:50-10:00) therefore misses the earlier run, and a later KR slot sends again.
    A relative lookback from *now* still catches delayed same-session duplicates
    without colliding with the later US close (~14h after KR).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    since = now - timedelta(hours=lookback_hours)
    current_id = int(current_run_id)

    for run in workflow_runs:
        run_id = run.get("id")
        if run_id is None or int(run_id) == current_id:
            continue

        created = parse_github_datetime(run.get("created_at"))
        if created is None or created < since or created > now:
            continue

        status = str(run.get("status") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        if conclusion == "success" or status in ACTIVE_STATUSES:
            return True

    return False


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = parse_github_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid --now timestamp: {value}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decide whether a scheduled daily report should skip delivery."
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--now")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    args = parser.parse_args(argv)

    payload = json.load(sys.stdin)
    if isinstance(payload, Mapping):
        runs = payload.get("workflow_runs", [])
    else:
        runs = payload

    skip = should_skip_duplicate_delivery(
        runs,
        current_run_id=args.run_id,
        now=_parse_now(args.now),
        lookback_hours=args.lookback_hours,
    )
    print("skip=true" if skip else "skip=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
