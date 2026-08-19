import sys
import unittest
import uuid
from pathlib import Path

from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import ChildWeightsUpdate


class ChildWeightSchemaTests(unittest.TestCase):
    def test_accepts_integer_percent(self):
        body = ChildWeightsUpdate(
            items=[{"todo_id": uuid.uuid4(), "percent": 40}]
        )
        self.assertEqual(body.items[0].percent, 40)

    def test_rejects_decimal_percent(self):
        with self.assertRaises(ValidationError):
            ChildWeightsUpdate(
                items=[{"todo_id": uuid.uuid4(), "percent": 40.5}]
            )

    def test_rejects_percent_outside_range(self):
        for value in (-1, 101):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ChildWeightsUpdate(
                    items=[{"todo_id": uuid.uuid4(), "percent": value}]
                )


if __name__ == "__main__":
    unittest.main()
