#!/usr/bin/env python3
"""End-to-end memory system test via Zulip + container verification."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ZULIP_URL = "https://127.0.0.1:18443"
ADMIN_EMAIL = "traceforge-admin@example.local"
ADMIN_KEY = "uNeUOmIl5czk5rbtP1iWizQseaprosDI"
STREAM = "sandbox"
TOPIC = "memory-system-test"
MARKER = f"MEM_E2E_{int(time.time())}"


def zulip_post(path: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        f"{ZULIP_URL}{path}",
        data=body,
        method="POST",
        headers={"Authorization": _basic_auth(ADMIN_EMAIL, ADMIN_KEY)},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def zulip_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{ZULIP_URL}{path}?{query}",
        headers={"Authorization": _basic_auth(ADMIN_EMAIL, ADMIN_KEY)},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def _basic_auth(email: str, api_key: str) -> str:
    import base64

    token = base64.b64encode(f"{email}:{api_key}".encode()).decode()
    return f"Basic {token}"


def send_message(content: str) -> int:
    payload = {
        "type": "stream",
        "to": STREAM,
        "topic": TOPIC,
        "content": content,
    }
    result = zulip_post("/api/v1/messages", payload)
    if result.get("result") != "success":
        raise RuntimeError(f"send failed: {result}")
    return int(result["id"])


def wait_for_bot_reply(after_id: int, timeout: float = 90.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = zulip_get(
            "/api/v1/messages",
            {
                "anchor": str(after_id),
                "num_before": 0,
                "num_after": 50,
                "narrow": json.dumps(
                    [
                        {"operator": "stream", "operand": STREAM},
                        {"operator": "topic", "operand": TOPIC},
                    ]
                ),
            },
        )
        for message in data.get("messages", []):
            if int(message.get("id", 0)) <= after_id:
                continue
            if str(message.get("sender_email", "")).lower() == "jarvis-bot@traceforge.local":
                return str(message.get("content") or "")
        time.sleep(2)
    raise TimeoutError("Jarvis did not reply in time")


def ingest(payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:19090/api/events/zulip",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.loads(res.read().decode("utf-8"))


def main() -> int:
    issues: list[str] = []
    print(f"=== Memory E2E marker: {MARKER} ===")

    # 1) remember preference via Zulip
    msg_id = send_message(f"@**Jarvis** 记住：{MARKER} 以后请用简洁中文回复我。")
    print(f"sent remember request id={msg_id}")
    try:
        reply = wait_for_bot_reply(msg_id)
        print("remember reply:", reply[:200].replace("\n", " "))
    except Exception as exc:
        issues.append(f"remember zulip: {exc}")

    time.sleep(3)

    # 2) search memory via Zulip
    msg_id = send_message(f"@**Jarvis** 用 memory 搜索一下 {MARKER} 相关记忆，告诉我找到了什么。")
    print(f"sent search request id={msg_id}")
    try:
        reply = wait_for_bot_reply(msg_id)
        print("search reply:", reply[:300].replace("\n", " "))
        if MARKER not in reply and "简洁" not in reply and "偏好" not in reply:
            issues.append("search reply did not mention marker or preference")
    except Exception as exc:
        issues.append(f"search zulip: {exc}")

    time.sleep(3)

    # 3) todo create -> memory write (direct ingest for deterministic subtree)
    ingest_payload = {
        "id": f"mem-test-{MARKER}",
        "workspace_id": "default",
        "sender_id": "8",
        "sender_email": ADMIN_EMAIL,
        "sender_full_name": "TraceForge Admin",
        "stream_name": STREAM,
        "topic": TOPIC,
        "text": f"@Jarvis 给 Neymar 创建一个 todo：{MARKER} 记忆回归验证",
    }
    result = ingest(ingest_payload)
    print("todo ingest intent:", result.get("result", {}).get("intent"))
    evidence = result.get("result", {}).get("evidence") or []
    tool_calls = [e for e in evidence if isinstance(e, dict) and e.get("type") == "tool_call"]
    print("tool calls:", [t.get("tool_name") for t in tool_calls])

    time.sleep(2)

    # 4) verify container memory files via docker exec helper script output
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
decision = store.read_file('memory/DECISION.md')
daily = store.read_file('memory/2026-09-02.md') if store.read_file('memory/2026-09-02.md') else ''
prefs = list((store.preferences_root).glob('*.md'))
pref_text = ''
for p in prefs:
    if p.name != 'README.md':
        t = p.read_text(encoding='utf-8')
        if marker in t:
            pref_text = t
            break
hits = idx.search(marker, limit=5)
print('DECISION_HAS', marker in decision)
print('DAILY_HAS', marker in daily)
print('PREF_HAS', bool(pref_text))
print('SEARCH_HITS', len(hits))
print('EMBEDDER', type(idx.embedder).__name__ if idx.embedder else None)
print('MODE', idx.search_mode)
""",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(check.stdout)
    if check.returncode != 0:
        issues.append(f"container verify failed: {check.stderr}")
    else:
        lines = dict(line.split(" ", 1) if " " in line else (line, "") for line in check.stdout.splitlines() if line)
        if lines.get("DECISION_HAS") != "True":
            issues.append("DECISION.md missing todo marker")
        if lines.get("DAILY_HAS") != "True":
            issues.append("daily missing todo marker")
        if lines.get("SEARCH_HITS", "0") == "0":
            issues.append("memory index search returned 0 hits for marker")
        if lines.get("EMBEDDER") != "LocalEmbeddingProvider":
            issues.append(f"expected LocalEmbeddingProvider, got {lines.get('EMBEDDER')}")

    if issues:
        print("\nISSUES:")
        for item in issues:
            print("-", item)
        return 1
    print("\nAll memory checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
