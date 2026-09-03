"""Light syntax checks on pushed files (deterministic; no auto-commit)."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SyntaxFinding:
    path: str
    language: str
    line: int | None
    message: str
    suggestion: str | None = None


_SUPPORTED = {
    ".py": "python",
    ".json": "json",
}


def collect_changed_paths(commits: Iterable[dict]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified"):
            items = commit.get(key) or []
            if not isinstance(items, list):
                continue
            for item in items:
                path = str(item or "").strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                paths.append(path)
    return paths


def language_for_path(path: str) -> str | None:
    lower = path.lower()
    for suffix, lang in _SUPPORTED.items():
        if lower.endswith(suffix):
            return lang
    return None


def check_syntax(*, path: str, content: str) -> list[SyntaxFinding]:
    lang = language_for_path(path)
    if lang is None:
        return []
    if lang == "python":
        return _check_python(path, content)
    if lang == "json":
        return _check_json(path, content)
    return []


def format_findings_markdown(
    findings: list[SyntaxFinding],
    *,
    checked: int,
    skipped: list[str],
) -> str:
    lines: list[str] = []
    if not findings:
        lines.append(f"语法检查：已检 {checked} 个文件，**未发现**可识别语法错误。")
    else:
        lines.append(f"语法检查：已检 {checked} 个文件，发现 **{len(findings)}** 处问题：")
        for finding in findings[:12]:
            loc = f":{finding.line}" if finding.line else ""
            lines.append(f"- `{finding.path}{loc}` ({finding.language}): {finding.message}")
            if finding.suggestion:
                lines.append(f"  - 建议: {finding.suggestion}")
        if len(findings) > 12:
            lines.append(f"- …另有 {len(findings) - 12} 处未列出")
    if skipped:
        preview = ", ".join(f"`{p}`" for p in skipped[:8])
        more = f" 等 {len(skipped)} 个" if len(skipped) > 8 else ""
        lines.append(f"未检查（非 py/json 或拉取失败）: {preview}{more}")
    lines.append("_说明：仅报告与建议，不会自动改仓库（非 Code Agent）。_")
    return "\n".join(lines)


def _check_python(path: str, content: str) -> list[SyntaxFinding]:
    try:
        ast.parse(content, filename=path)
        return []
    except SyntaxError as exc:
        suggestion = _python_suggestion(exc, content)
        return [
            SyntaxFinding(
                path=path,
                language="python",
                line=exc.lineno,
                message=str(exc.msg or exc).strip() or "SyntaxError",
                suggestion=suggestion,
            )
        ]


def _check_json(path: str, content: str) -> list[SyntaxFinding]:
    try:
        json.loads(content)
        return []
    except json.JSONDecodeError as exc:
        return [
            SyntaxFinding(
                path=path,
                language="json",
                line=exc.lineno,
                message=exc.msg,
                suggestion="检查逗号、引号与括号是否成对；可用 json.tool 校验。",
            )
        ]


def _python_suggestion(exc: SyntaxError, content: str) -> str:
    msg = (exc.msg or "").lower()
    if "unexpected eof" in msg or "was never closed" in msg:
        return "检查括号/引号/三引号是否闭合。"
    if "invalid syntax" in msg and exc.lineno:
        line = _line_at(content, exc.lineno)
        if line.rstrip().endswith(":"):
            return "该行以冒号结尾时，下一行需要缩进代码块。"
        if re.search(r"\bprint\s+[^(]", line):
            return "Python 3 中 print 需要写成函数调用：print(...)。"
    if "expected ':'" in msg:
        return "if/for/def/class 等语句末尾需要冒号 `:`。"
    if "unterminated string" in msg:
        return "字符串未闭合，检查引号配对。"
    return "按报错行附近修正语法后再推送。"


def _line_at(content: str, lineno: int) -> str:
    lines = content.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""
