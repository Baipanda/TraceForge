#!/usr/bin/env python3
"""Re-test progress-sop on Zulip after bot-loop fix."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

ZULIP_URL = "https://127.0.0.1:18443"
ADMIN_EMAIL = "traceforge-admin@example.local"
ADMIN_KEY = Path("/tmp/admin_zulip_key.txt").read_text(encoding="utf-8").strip()
STREAM = "sandbox"
TOPIC = f"sop-retest-{int(time.time())}"


def _auth() -> str:
    import base64

    return "Basic " + base64.b64encode(f"{ADMIN_EMAIL}:{ADMIN_KEY}".encode()).decode()


def _ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def zulip_post(path: str, data: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{ZULIP_URL}{path}",
        data=urllib.parse.urlencode(data).encode(),
        method="POST",
        headers={"Authorization": _auth()},
    )
    with urllib.request.urlopen(req, context=_ctx(), timeout=60) as res:
        return json.loads(res.read().decode())


def zulip_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{ZULIP_URL}{path}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": _auth()},
    )
    with urllib.request.urlopen(req, context=_ctx(), timeout=60) as res:
        return json.loads(res.read().decode())


def send(content: str) -> int:
    result = zulip_post(
        "/api/v1/messages",
        {"type": "stream", "to": STREAM, "topic": TOPIC, "content": content},
    )
    if result.get("result") != "success":
        raise RuntimeError(result)
    return int(result["id"])


def plain(html: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or ""))).strip()


def wait_jarvis(after_id: int, *, timeout: float = 150.0) -> tuple[int, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = zulip_get(
            "/api/v1/messages",
            {
                "anchor": str(after_id),
                "num_before": "0",
                "num_after": "50",
                "narrow": json.dumps(
                    [
                        {"operator": "stream", "operand": STREAM},
                        {"operator": "topic", "operand": TOPIC},
                    ]
                ),
            },
        )
        for message in data.get("messages", []):
            mid = int(message.get("id") or 0)
            if mid <= after_id:
                continue
            email = str(message.get("sender_email") or "").lower()
            if "jarvis-bot@" in email:
                return mid, plain(str(message.get("content") or ""))
        time.sleep(2)
    raise TimeoutError(f"no Jarvis reply after {after_id}")


def count_bot_msgs_after(after_id: int) -> dict[str, int]:
    data = zulip_get(
        "/api/v1/messages",
        {
            "anchor": str(after_id),
            "num_before": "0",
            "num_after": "100",
            "narrow": json.dumps(
                [
                    {"operator": "stream", "operand": STREAM},
                    {"operator": "topic", "operand": TOPIC},
                ]
            ),
        },
    )
    counts = {"jarvis": 0, "repoaudit": 0, "other": 0}
    for message in data.get("messages", []):
        mid = int(message.get("id") or 0)
        if mid <= after_id:
            continue
        email = str(message.get("sender_email") or "").lower()
        if "jarvis-bot@" in email:
            counts["jarvis"] += 1
        elif "repoaudit" in email:
            counts["repoaudit"] += 1
        else:
            counts["other"] += 1
    return counts


def main() -> int:
    issues: list[str] = []
    print(f"=== SOP retest topic #{STREAM}/{TOPIC} ===")

    mid = send("@**Jarvis** 项目进度：todo-show")
    print(f"[1] trigger id={mid}")
    try:
        mid, text = wait_jarvis(mid)
        print("[1] scope:", text[:260])
        if not all(x in text for x in ("1.", "2.", "3.")):
            issues.append("HITL-A missing numbered menu 1/2/3")
        m = re.search(r"run_id[：:`\s]*([0-9a-fA-F\-]{8,})", text)
        if not m:
            issues.append("missing run_id")
            run_id = ""
        else:
            run_id = m.group(1).strip("`")
            print("[1] run_id=", run_id)
    except Exception as exc:
        issues.append(f"trigger: {exc}")
        run_id = ""

    if run_id:
        mid = send(
            f"@**Jarvis** sop continue run_id={run_id} window=7 include_audit=0 focus=blocked"
        )
        print(f"[2] continue(skip audit) id={mid}")
        try:
            mid, text = wait_jarvis(mid, timeout=180)
            print("[2] report:", text[:280])
            if "progress-sop" not in text and "项目进度体检" not in text:
                issues.append("report missing progress-sop heading")
            if "HITL-B" not in text and "后续动作" not in text:
                issues.append("missing HITL-B cue")
            if not all(x in text for x in ("1.", "2.", "3.")):
                issues.append("HITL-B missing numbered menu")
        except Exception as exc:
            issues.append(f"continue: {exc}")

        mid = send(f"@**Jarvis** sop followup run_id={run_id} action=noop")
        print(f"[3] followup noop id={mid}")
        try:
            mid, text = wait_jarvis(mid, timeout=90)
            print("[3] followup:", text[:220])
            if "结束" not in text and "阅览" not in text and "done" not in text.lower():
                # still ok if it says already done / phase
                if "phase" not in text.lower() and "run" not in text.lower():
                    issues.append(f"unexpected followup text: {text[:120]}")
        except Exception as exc:
            issues.append(f"followup: {exc}")

    # Anti-loop: after final reply, bot traffic should stay flat.
    last = mid
    time.sleep(8)
    counts = count_bot_msgs_after(last)
    print("[4] bot msgs after final:", counts)
    if counts["jarvis"] or counts["repoaudit"]:
        issues.append(f"possible bot loop after finish: {counts}")

    if issues:
        print("\nFAILED:")
        for item in issues:
            print("-", item)
        return 1
    print("\nSOP retest passed.")
    print(f"See Zulip: #{STREAM} / {TOPIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
