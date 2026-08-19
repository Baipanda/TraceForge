import sys
import unittest
import uuid
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import TodoCreate, TodoUpdate


class BugFlagSchemaTests(unittest.TestCase):
    def test_existing_create_payload_defaults_to_non_bug(self):
        body = TodoCreate(title="普通事项", subtree_id=uuid.uuid4())

        self.assertFalse(body.is_bug)

    def test_create_accepts_bug_flag(self):
        body = TodoCreate(title="登录失败", subtree_id=uuid.uuid4(), is_bug=True)

        self.assertTrue(body.is_bug)

    def test_update_tracks_explicit_false(self):
        body = TodoUpdate(is_bug=False)

        self.assertIn("is_bug", body.model_fields_set)
        self.assertFalse(body.is_bug)


if __name__ == "__main__":
    unittest.main()
