"""Read-only Project Admin API client (Scope step source of truth)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from traceforge.config import TraceForgeSettings, get_settings


class ProjectAdminError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProjectAdminClient:
    def __init__(self, settings: TraceForgeSettings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return (self.settings.project_admin_url or "http://127.0.0.1:18081").rstrip("/")

    def resolve(
        self,
        *,
        project_id: str = "",
        stream: str = "",
        topic: str = "",
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if project_id.strip():
            params["project_id"] = project_id.strip()
        if stream.strip():
            params["stream"] = stream.strip()
        if topic.strip():
            params["topic"] = topic.strip()
        if not params:
            raise ProjectAdminError("provide project_id or stream+topic", status_code=400)
        return self._get("/api/projects/resolve", params)

    def get(self, project_id: str) -> dict[str, Any]:
        pid = (project_id or "").strip()
        if not pid:
            raise ProjectAdminError("project_id is required", status_code=400)
        return self._get(f"/api/projects/{urllib.parse.quote(pid, safe='')}")

    def create_report(
        self,
        *,
        project_id: str,
        title: str,
        markdown_body: str,
        pipeline: str = "progress-sop",
        meta_json: dict[str, Any] | None = None,
        created_by: str = "progress-sop",
        mentor: str = "traceforge-admin",
    ) -> dict[str, Any]:
        del mentor  # reports endpoint is open for SOP writeback
        payload = {
            "project_id": project_id,
            "title": title,
            "pipeline": pipeline,
            "markdown_body": markdown_body,
            "meta_json": meta_json or {},
            "created_by": created_by,
        }
        return self._post(
            "/api/reports",
            payload,
            headers={"Content-Type": "application/json"},
        )

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        return self._request("GET", f"{path}{query}")

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._request("POST", path, body=body, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url=url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ProjectAdminError(
                f"Project Admin HTTP {exc.code}: {detail}",
                status_code=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise ProjectAdminError(
                f"Project Admin unreachable at {self.base_url}: {exc.reason}"
            ) from exc
