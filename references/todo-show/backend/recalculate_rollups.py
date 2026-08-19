"""Recalculate parent Todo work and sync rollups."""
from main import mark_parent_rollups_reconciled, recalculate_parent_rollups


if __name__ == "__main__":
    print(recalculate_parent_rollups())
    mark_parent_rollups_reconciled()
