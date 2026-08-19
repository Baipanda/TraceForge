import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import _parent_sync_rollup_action, _parent_work_rollup_action


class ParentWorkRollupTests(unittest.TestCase):
    def test_completes_when_no_child_is_pending(self):
        action = _parent_work_rollup_action(
            "pending", False, child_count=3, pending_count=0,
            child_weight_total=100, dependencies_completed=True,
        )
        self.assertEqual(action, "complete")

    def test_cancelled_and_expired_children_count_as_ended(self):
        action = _parent_work_rollup_action(
            "pending", False, child_count=2, pending_count=0,
            child_weight_total=100, dependencies_completed=True,
        )
        self.assertEqual(action, "complete")

    def test_does_not_complete_when_dependency_is_unfinished(self):
        action = _parent_work_rollup_action(
            "pending", False, child_count=2, pending_count=0,
            child_weight_total=100, dependencies_completed=False,
        )
        self.assertIsNone(action)

    def test_reopens_only_system_completed_parent(self):
        self.assertEqual(
            _parent_work_rollup_action("completed", True, 2, 1, 100, True),
            "reopen",
        )
        self.assertIsNone(
            _parent_work_rollup_action("completed", False, 2, 1, 100, True)
        )

    def test_reopens_system_completed_parent_when_dependency_reopens(self):
        self.assertEqual(
            _parent_work_rollup_action("completed", True, 2, 0, 100, False),
            "reopen",
        )

    def test_parent_without_children_is_unchanged(self):
        self.assertIsNone(
            _parent_work_rollup_action("pending", False, 0, 0, 0, True)
        )

    def test_parent_with_own_work_is_not_auto_completed(self):
        self.assertIsNone(
            _parent_work_rollup_action("pending", False, 2, 0, 80, True)
        )

    def test_system_completed_parent_reopens_when_weight_drops_below_100(self):
        self.assertEqual(
            _parent_work_rollup_action("completed", True, 2, 0, 80, True),
            "reopen",
        )


class ParentSyncRollupTests(unittest.TestCase):
    def test_syncs_when_all_active_children_are_synced(self):
        action = _parent_sync_rollup_action(
            "pending", 3, active_count=2, unsynced_count=0,
            already_synced_today=False, has_active_rollup_today=False,
        )
        self.assertEqual(action, "sync")

    def test_ended_children_are_ignored(self):
        action = _parent_sync_rollup_action(
            "pending", 4, active_count=1, unsynced_count=0,
            already_synced_today=False, has_active_rollup_today=False,
        )
        self.assertEqual(action, "sync")

    def test_does_not_sync_without_active_children(self):
        self.assertIsNone(
            _parent_sync_rollup_action("pending", 2, 0, 0, False, False)
        )

    def test_revokes_rollup_when_child_becomes_unsynced(self):
        action = _parent_sync_rollup_action(
            "pending", 2, active_count=2, unsynced_count=1,
            already_synced_today=True, has_active_rollup_today=True,
        )
        self.assertEqual(action, "revoke")

    def test_manual_sync_is_not_revoked(self):
        self.assertIsNone(
            _parent_sync_rollup_action("pending", 2, 2, 1, True, False)
        )


if __name__ == "__main__":
    unittest.main()
