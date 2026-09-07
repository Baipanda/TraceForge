#!/usr/bin/env python3
"""Zulip e2e: memory fluency + progress-sop HITL numbered choices."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ZULIP_URL = "https://127.0.0.1:18443"
ADMIN_EMAIL = "traceforge-admin@example.local"
ADMIN_KEY_PATH = Path("/tmp/admin_zulip_key.txt")
STREAM = "sandbox"
TOPIC_MEMORY = "memory-fluency-test"
TOPIC_SOP = "todo-show开发"
MARKER = f"MEM_FLOW_{int(time.time())}"
API = "http://127.0.0.1:19090"


def _admin_key() -> str:
    if ADMIN_KEY_PATH.exists():
        return ADMIN_KEY_PATH.read_text(encoding="utf-8").strip()
    env = Path("/home/baijiaoyang/workspace/TraceForge/.env")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("TRACEFORGE_ZULIP_API_KEY="):
            # prefer admin key file; fallback unused
            break
    raise SystemExit(f"missing admin key at {ADMIN_KEY_PATH}")


def _auth(email: str, key: str) -> str:
    import base64

    return "Basic " + base64.b64encode(f"{email}:{key}".encode()).decode()


def zulip_post(path: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        f"{ZULIP_URL}{path}",
        data=body,
        method="POST",
        headers={"Authorization": _auth(ADMIN_EMAIL, _admin_key())},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def zulip_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{ZULIP_URL}{path}?{query}",
        headers={"Authorization": _auth(ADMIN_EMAIL, _admin_key())},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def send(topic: str, content: str) -> int:
    result = zulip_post(
        "/api/v1/messages",
        {"type": "stream", "to": STREAM, "topic": topic, "content": content},
    )
    if result.get("result") != "success":
        raise RuntimeError(f"send failed: {result}")
    return int(result["id"])


def wait_bot_reply(topic: str, after_id: int, *, timeout: float = 120.0) -> tuple[int, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = zulip_get(
            "/api/v1/messages",
            {
                "anchor": str(after_id),
                "num_before": "0",
                "num_after": "40",
                "narrow": json.dumps(
                    [
                        {"operator": "stream", "operand": STREAM},
                        {"operator": "topic", "operand": topic},
                    ]
                ),
            },
        )
        for message in data.get("messages", []):
            mid = int(message.get("id") or 0)
            if mid <= after_id:
                continue
            email = str(message.get("sender_email") or "").lower()
            if "jarvis" in email:
                return mid, str(message.get("content") or "")
        time.sleep(2)
    raise TimeoutError(f"Jarvis did not reply in #{STREAM}/{topic} after {after_id}")


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def main() -> int:
    issues: list[str] = []
    print(f"=== marker {MARKER} ===")

    # --- Memory fluency ---
    mid = send(TOPIC_MEMORY, f"@**Jarvis** 记住：{MARKER} 以后请用简洁中文，并在回复里带上该标记。")
    print(f"[memory] remember sent id={mid}")
    try:
        mid, reply = wait_bot_reply(TOPIC_MEMORY, mid)
        print("[memory] remember reply:", strip_html(reply)[:180].replace("\n", " "))
    except Exception as exc:
        issues.append(f"memory remember: {exc}")

    mid = send(TOPIC_MEMORY, f"@**Jarvis** 用 memory.search 搜索 {MARKER}，告诉我找到了什么。")
    print(f"[memory] search sent id={mid}")
    try:
        mid, reply = wait_bot_reply(TOPIC_MEMORY, mid)
        plain = strip_html(reply)
        print("[memory] search reply:", plain[:240].replace("\n", " "))
        if MARKER not in plain and "简洁" not in plain:
            issues.append("memory search reply missing marker/preference cue")
    except Exception as exc:
        issues.append(f"memory search: {exc}")

    # --- progress-sop ---
    mid = send(TOPIC_SOP, "@**Jarvis** 项目进度：todo-show")
    print(f"[sop] trigger sent id={mid}")
    run_id = ""
    try:
        mid, reply = wait_bot_reply(TOPIC_SOP, mid, timeout=150)
        plain = strip_html(reply)
        print("[sop] scope reply:", plain[:280].replace("\n", " "))
        if "1." not in plain or "2." not in plain or "3." not in plain:
            issues.append("HITL-A menu missing numbered 1/2/3 in reply text")
        m = re.search(r"run_id[：:`\s]*([0-9a-fA-F\-]{8,})", plain)
        if not m:
            issues.append("scope reply missing run_id")
        else:
            run_id = m.group(1).strip("`")
            print("[sop] run_id=", run_id)
    except Exception as exc:
        issues.append(f"sop trigger: {exc}")

    if run_id:
        # Choose option 3 via continue command (skip audit for speed)
        mid = send(
            TOPIC_SOP,
            f"@**Jarvis** sop continue run_id={run_id} window=7 include_audit=0 focus=blocked",
        )
        print(f"[sop] continue(3/skip-audit) sent id={mid}")
        try:
            mid, reply = wait_bot_reply(TOPIC_SOP, mid, timeout=180)
            plain = strip_html(reply)
            print("[sop] report reply:", plain[:280].replace("\n", " "))
            if "HITL-B" not in plain and "后续动作" not in plain:
                issues.append("report missing HITL-B cue")
            if "1." not in plain or "2." not in plain:
                issues.append("HITL-B menu missing numbered options")
        except Exception as exc:
            issues.append(f"sop continue: {exc}")

        mid = send(TOPIC_SOP, f"@**Jarvis** sop followup run_id={run_id} action=noop")
        print(f"[sop] followup noop sent id={mid}")
        try:
            mid, reply = wait_bot_reply(TOPIC_SOP, mid, timeout=90)
            plain = strip_html(reply)
            print("[sop] followup reply:", plain[:200].replace("\n", " "))
        except Exception as exc:
            issues.append(f"sop followup: {exc}")

    # Container memory index spot-check
    try:
        import subprocess

        check = subprocess.run(
            [
                "docker",
                "exec",
                "traceforge-app",
                "python",
                "-c",
                f"""
from traceforge.config import get_settings
from traceforge.memory.factory import build_markdown_memory_index
from traceforge.memory.markdown_store import MarkdownMemoryStore
marker = {MARKER!r}
s = get_settings()
store = MarkdownMemoryStore()
idx = build_markdown_memory_index(s.traceforge_db_path, store, settings=s)
hits = idx.search_detailed(marker, limit=5)
print('SEARCH_HITS', hits.count if False else len(hits.hits))
print('DEGRADED', hits.degraded)
print('MODE', hits.effective_mode)
print('REASON', hits.degrade_reason)
""",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        print("[memory] container:\n", check.stdout)
        if check.returncode != 0:
            issues.append(f"container memory check failed: {check.stderr[:300]}")
        elif "SEARCH_HITS 0" in check.stdout:
            issues.append("container memory search returned 0 hits for marker")
    except Exception as exc:
        issues.append(f"container check: {exc}")

    if issues:
        print("\nISSUES:")
        for item in issues:
            print("-", item)
        return 1
    print("\nAll memory + SOP checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
