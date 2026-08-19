import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import _add_sync_interval, _build_sync_info, _sync_day_bounds, _sync_due_condition


class SyncStatusTests(unittest.TestCase):
    def test_closed_todo_has_no_next_sync(self):
        now = datetime.now(timezone.utc)
        next_sync_at, meta = _build_sync_info("completed", "weekly", now, None)

        self.assertIsNone(next_sync_at)
        self.assertEqual(meta.code, "closed")

    def test_missing_frequency_is_not_configured(self):
        now = datetime.now(timezone.utc)
        next_sync_at, meta = _build_sync_info("pending", None, now, None)

        self.assertIsNone(next_sync_at)
        self.assertEqual(meta.code, "not_configured")

    def test_frequency_status_uses_shanghai_calendar_days(self):
        now = datetime(2026, 7, 14, 4, tzinfo=timezone.utc)

        _, overdue = _build_sync_info(
            "pending", "daily", datetime(2026, 7, 11, 4, tzinfo=timezone.utc), None, now=now
        )
        _, due_today = _build_sync_info(
            "pending", "daily", datetime(2026, 7, 13, 4, tzinfo=timezone.utc), None, now=now
        )
        _, scheduled = _build_sync_info(
            "pending", "weekly", datetime(2026, 7, 14, 4, tzinfo=timezone.utc), None, now=now
        )

        self.assertEqual(overdue.code, "overdue")
        self.assertEqual(due_today.code, "due_today")
        self.assertEqual(scheduled.code, "scheduled")

    def test_unconfirmed_progress_recorded_today_is_filled_today(self):
        now = datetime(2026, 7, 14, 4, tzinfo=timezone.utc)
        last_progress_at = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
        last_confirmed_at = datetime(2026, 7, 10, 1, tzinfo=timezone.utc)

        next_sync_at, meta = _build_sync_info(
            "pending",
            "daily",
            now - timedelta(days=10),
            last_progress_at,
            last_progress_confirmed_at=None,
            last_confirmed_at=last_confirmed_at,
            now=now,
        )

        self.assertEqual(meta.code, "filled_today")
        self.assertEqual(next_sync_at, datetime(2026, 7, 11, 1, tzinfo=timezone.utc))

    def test_confirmed_progress_today_is_synced_today(self):
        now = datetime(2026, 7, 14, 4, tzinfo=timezone.utc)
        recorded_at = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
        confirmed_at = datetime(2026, 7, 14, 2, tzinfo=timezone.utc)

        next_sync_at, meta = _build_sync_info(
            "pending",
            "daily",
            now - timedelta(days=10),
            recorded_at,
            last_progress_confirmed_at=confirmed_at,
            last_confirmed_at=confirmed_at,
            now=now,
        )

        self.assertEqual(meta.code, "synced_today")
        self.assertEqual(next_sync_at, datetime(2026, 7, 15, 2, tzinfo=timezone.utc))

    def test_unconfirmed_progress_becomes_confirmation_overdue(self):
        now = datetime(2026, 7, 16, 4, tzinfo=timezone.utc)
        recorded_at = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
        last_confirmed_at = datetime(2026, 7, 10, 1, tzinfo=timezone.utc)

        next_sync_at, meta = _build_sync_info(
            "pending",
            "daily",
            now - timedelta(days=20),
            recorded_at,
            last_progress_confirmed_at=None,
            last_confirmed_at=last_confirmed_at,
            now=now,
        )

        self.assertEqual(meta.code, "pending_confirmation_overdue")
        self.assertEqual(meta.label, "待确认（已逾期）")
        self.assertEqual(meta.tone, "danger")
        self.assertEqual(next_sync_at, datetime(2026, 7, 11, 1, tzinfo=timezone.utc))

    def test_monthly_frequency_clamps_end_of_month(self):
        january_end = datetime(2026, 1, 31, 9, tzinfo=timezone.utc)

        self.assertEqual(_add_sync_interval(january_end, "monthly").day, 28)

    def test_sync_day_uses_shanghai_calendar_boundaries(self):
        now = datetime(2026, 7, 13, 17, tzinfo=timezone.utc)

        today_start, tomorrow_start = _sync_day_bounds(now)

        self.assertEqual(today_start, datetime(2026, 7, 13, 16, tzinfo=timezone.utc))
        self.assertEqual(tomorrow_start, datetime(2026, 7, 14, 16, tzinfo=timezone.utc))

    def test_future_three_days_starts_tomorrow(self):
        now = datetime(2026, 7, 13, 17, tzinfo=timezone.utc)

        sql, params = _sync_due_condition("next_3_days", now)

        self.assertIn("t.status = 'pending'", sql)
        self.assertEqual(params[0], datetime(2026, 7, 14, 16, tzinfo=timezone.utc))
        self.assertEqual(params[1], datetime(2026, 7, 17, 16, tzinfo=timezone.utc))

    def test_synced_today_filter_uses_natural_day(self):
        now = datetime(2026, 7, 13, 17, tzinfo=timezone.utc)

        sql, params = _sync_due_condition("synced_today", now)

        self.assertIn("confirmed.last_confirmed_at", sql)
        self.assertEqual(params[0], datetime(2026, 7, 13, 16, tzinfo=timezone.utc))
        self.assertEqual(params[1], datetime(2026, 7, 14, 16, tzinfo=timezone.utc))

    def test_filled_today_filter_requires_unconfirmed_progress(self):
        now = datetime(2026, 7, 13, 17, tzinfo=timezone.utc)

        sql, params = _sync_due_condition("filled_today", now)

        self.assertIn("progress.confirmed_at IS NULL", sql)
        self.assertEqual(params[0], datetime(2026, 7, 13, 16, tzinfo=timezone.utc))
        self.assertEqual(params[1], datetime(2026, 7, 14, 16, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
