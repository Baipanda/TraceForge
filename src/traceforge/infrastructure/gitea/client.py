"""Gitea REST helpers for RepoAudit (raw file fetch)."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from traceforge.config import TraceForgeSettings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GiteaFileContent:
    path: str
    ref: str
    content: str
    truncated: bool = False


class GiteaApiClient:
    def __init__(self, settings: TraceForgeSettings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool((self.settings.gitea_url or "").strip() and (self.settings.gitea_token or "").strip())

    def fetch_raw_file(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        max_bytes: int = 200_000,
    ) -> GiteaFileContent | None:
        if not self.enabled:
            return None
        owner_q = urllib.parse.quote(owner, safe="")
        repo_q = urllib.parse.quote(repo, safe="")
        # Gitea raw API: /api/v1/repos/{owner}/{repo}/raw/{filepath}?ref=
        path_q = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/") if part)
        query = urllib.parse.urlencode({"ref": ref})
        api_path = f"/api/v1/repos/{owner_q}/{repo_q}/raw/{path_q}?{query}"
        try:
            raw = self._request_bytes("GET", api_path)
        except Exception as exc:
            logger.warning("Gitea raw fetch failed for %s@%s: %s", path, ref, exc)
            return None
        truncated = len(raw) > max_bytes
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        return GiteaFileContent(path=path, ref=ref, content=text, truncated=truncated)

    def _request_bytes(self, method: str, path: str, timeout: float = 30) -> bytes:
        base = (self.settings.gitea_api_connect_url or self.settings.gitea_url).rstrip("/")
        url = f"{base}{path}"
        headers = {
            "Authorization": f"token {self.settings.gitea_token}",
            "Accept": "application/json, text/plain, */*",
        }
        logical = urllib.parse.urlparse(self.settings.gitea_url.rstrip("/"))
        connect = urllib.parse.urlparse(base)
        if logical.netloc and logical.netloc != connect.netloc:
            headers["Host"] = logical.netloc
        request = urllib.request.Request(url=url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gitea API HTTP {exc.code}: {detail}") from exc

    def _request_json(self, method: str, path: str) -> dict[str, Any]:
        raw = self._request_bytes(method, path)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("Gitea API expected object")
        return data
