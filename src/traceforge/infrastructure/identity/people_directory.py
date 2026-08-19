from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IdentityRecord:
    canonical_name: str
    email: str
    zulip_username: str | None = None
    database_username: str | None = None
    aliases: tuple[str, ...] = ()
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "email": self.email,
            "zulip_username": self.zulip_username,
            "database_username": self.database_username,
            "aliases": list(self.aliases),
            "notes": self.notes,
        }


class PeopleDirectory:
    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else self._default_workspace_root()
        self.people_path = self.workspace_root / "people.json"
        self._records = self._load_records()

    def list(self) -> list[IdentityRecord]:
        return list(self._records)

    def resolve(self, query: str | None) -> IdentityRecord | None:
        if not query:
            return None
        needle = query.strip().lower()
        if not needle:
            return None
        for record in self._records:
            candidates = {
                record.canonical_name.lower(),
                record.email.lower(),
            }
            if record.zulip_username:
                candidates.add(record.zulip_username.lower())
            if record.database_username:
                candidates.add(record.database_username.lower())
            candidates.update(alias.lower() for alias in record.aliases)
            if needle in candidates:
                return record
        return None

    def _load_records(self) -> list[IdentityRecord]:
        if self.people_path.exists():
            return [_record_from_dict(item) for item in _load_json(self.people_path)]
        return [_default_neymar_record()]

    def _default_workspace_root(self) -> Path:
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "workspace"
            if candidate.exists():
                return candidate
        return Path.cwd() / "workspace"


def _load_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"People file must be a JSON list: {path}")
    result: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            result.append(item)
    return result


def _record_from_dict(data: dict[str, Any]) -> IdentityRecord:
    aliases = data.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []
    return IdentityRecord(
        canonical_name=str(data.get("canonical_name") or data.get("name") or ""),
        email=str(data.get("email") or ""),
        zulip_username=_optional_str(data.get("zulip_username")),
        database_username=_optional_str(data.get("database_username")),
        aliases=tuple(str(item) for item in aliases if isinstance(item, str)),
        notes=_optional_str(data.get("notes")),
    )


def _default_neymar_record() -> IdentityRecord:
    return IdentityRecord(
        canonical_name="Neymar",
        email="neymar@traceforge.local",
        zulip_username="Neymar",
        database_username="neymar",
        aliases=("Neymar Jr", "Neymar Junior"),
        notes="TraceForge demo identity for Zulip/DB mapping.",
    )


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None

