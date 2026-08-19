import sys
import types
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

database = types.ModuleType("database")
database.execute = lambda *args, **kwargs: None
database.query = lambda *args, **kwargs: []
database.query_one = lambda *args, **kwargs: None
database.transaction = lambda *args, **kwargs: None
sys.modules["database"] = database

psycopg2 = types.ModuleType("psycopg2")
psycopg2_extras = types.ModuleType("psycopg2.extras")
psycopg2_extras.Json = lambda value: value
psycopg2.extras = psycopg2_extras
sys.modules["psycopg2"] = psycopg2
sys.modules["psycopg2.extras"] = psycopg2_extras

from main import _build_change_detail
from schemas import TodoUpdate


def test_update_tracks_explicit_null_fields():
    body = TodoUpdate(project_id=None, tracker_id=None)

    assert "project_id" in body.model_fields_set
    assert "tracker_id" in body.model_fields_set


def test_change_detail_records_null_clears():
    before = {"project_id": 3, "tracker_id": 12}
    detail = _build_change_detail(
        before,
        {"project_id": None, "tracker_id": None},
    )

    assert "项目: 3 -> 空" in detail
    assert "跟踪人: 12 -> 空" in detail


def test_change_detail_ignores_unchanged_values():
    before = {"priority": "normal", "watcher_ids": [1, 2]}
    detail = _build_change_detail(
        before,
        {"priority": "normal", "watcher_ids": [1, 2]},
    )

    assert detail == "无实际字段变化"
