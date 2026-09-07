import io
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch


sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.workflows.schedule_dedupe import main, should_skip_duplicate_delivery


class ScheduleDedupeTests(unittest.TestCase):
    def test_skips_when_prior_success_is_delayed_outside_legacy_utc_window(self):
        # GitHub delayed both KR crons by ~6 hours. The old 06:50-10:00 UTC
        # window missed the 13:25 success, so the 13:38 safety-net run sent again.
        now = datetime(2026, 9, 7, 13, 38, 38, tzinfo=timezone.utc)
        runs = [
            {
                "id": 34127349904,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-09-07T13:25:52Z",
            },
            {
                "id": 34128539434,
                "status": "in_progress",
                "conclusion": None,
                "created_at": "2026-09-07T13:38:38Z",
            },
        ]

        self.assertTrue(
            should_skip_duplicate_delivery(
                runs,
                current_run_id=34128539434,
                now=now,
            )
        )

    def test_does_not_skip_when_only_current_run_exists(self):
        now = datetime(2026, 9, 7, 13, 26, 0, tzinfo=timezone.utc)
        runs = [
            {
                "id": 34127349904,
                "status": "in_progress",
                "conclusion": None,
                "created_at": "2026-09-07T13:25:52Z",
            }
        ]

        self.assertFalse(
            should_skip_duplicate_delivery(
                runs,
                current_run_id=34127349904,
                now=now,
            )
        )

    def test_skips_in_progress_prior_run_in_lookback_window(self):
        now = datetime(2026, 9, 7, 7, 37, 10, tzinfo=timezone.utc)
        runs = [
            {
                "id": 1,
                "status": "in_progress",
                "conclusion": None,
                "created_at": "2026-09-07T07:07:05Z",
            },
            {
                "id": 2,
                "status": "queued",
                "conclusion": None,
                "created_at": "2026-09-07T07:37:10Z",
            },
        ]

        self.assertTrue(
            should_skip_duplicate_delivery(runs, current_run_id=2, now=now)
        )

    def test_does_not_skip_failed_prior_run(self):
        now = datetime(2026, 9, 7, 7, 37, 10, tzinfo=timezone.utc)
        runs = [
            {
                "id": 1,
                "status": "completed",
                "conclusion": "failure",
                "created_at": "2026-09-07T07:07:05Z",
            }
        ]

        self.assertFalse(
            should_skip_duplicate_delivery(runs, current_run_id=2, now=now)
        )

    def test_does_not_skip_us_run_after_morning_kr_delivery(self):
        now = datetime(2026, 9, 7, 21, 28, 10, tzinfo=timezone.utc)
        runs = [
            {
                "id": 1,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-09-07T07:07:05Z",
            }
        ]

        self.assertFalse(
            should_skip_duplicate_delivery(runs, current_run_id=2, now=now)
        )

    def test_cli_prints_skip_true_for_delayed_prior_success(self):
        payload = {
            "workflow_runs": [
                {
                    "id": 34127349904,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-09-07T13:25:52Z",
                },
                {
                    "id": 34128539434,
                    "status": "in_progress",
                    "conclusion": None,
                    "created_at": "2026-09-07T13:38:38Z",
                },
            ]
        }

        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main(
                [
                    "--run-id",
                    "34128539434",
                    "--now",
                    "2026-09-07T13:38:38Z",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "skip=true")


if __name__ == "__main__":
    unittest.main()
