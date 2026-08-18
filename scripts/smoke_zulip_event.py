from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:19090/api/events/zulip"
    payload = {
        "id": "smoke-event-1",
        "workspace_id": "demo",
        "sender_id": "25",
        "sender_email": "zhangsan@zulip.local",
        "sender_full_name": "张三",
        "stream_id": "security",
        "stream_name": "安全研发",
        "topic": "SQL 注入排查",
        "text": "@TraceForge 给李四发布一个 todo：检查认证模块 SQL 注入风险",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=10) as res:
        print(res.read().decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
