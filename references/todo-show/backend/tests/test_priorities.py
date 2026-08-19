import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from schemas import TODO_PRIORITIES


class PriorityTests(unittest.TestCase):
    def test_three_priorities_are_supported(self):
        self.assertEqual(TODO_PRIORITIES, ["low", "normal", "high"])


if __name__ == "__main__":
    unittest.main()
