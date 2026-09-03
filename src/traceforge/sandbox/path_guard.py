"""Resolve paths under a workspace root; reject escapes."""

from __future__ import annotations

from pathlib import Path


class PathGuardError(ValueError):
    """Raised when a path escapes the sandbox workspace root."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_under_root(root: Path, user_path: str | None, *, must_exist: bool = False) -> Path:
    """Return a resolved path that is strictly under ``root``.

    Follows symlinks via ``Path.resolve()`` so link-based escapes are rejected.
    """
    if user_path is None or not str(user_path).strip():
        raise PathGuardError("empty_path", "path is required")

    root_resolved = root.expanduser().resolve()
    raw = Path(str(user_path).strip())

    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (root_resolved / raw).resolve()

    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise PathGuardError(
            "path_escape",
            f"path escapes workspace root ({root_resolved}): {user_path}",
        ) from exc

    if must_exist and not candidate.exists():
        raise PathGuardError("not_found", f"path not found: {user_path}")

    return candidate
