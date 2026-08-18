"""TraceForge workspace management CLI placeholder.

后续用于本地调试 Skill、Tool、Agent Run 和数据库迁移。
业务动作应复用 TraceForge application/tool 层，不在脚本中复制实现。
"""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="traceforge-cli")
    parser.add_argument("--version", action="version", version="traceforge-cli 0.1.0")
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
