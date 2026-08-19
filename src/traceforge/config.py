from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path | None = None) -> None:
    env_path = path or Path(os.environ.get("TRACEFORGE_ENV_FILE", _default_env_path()))
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _default_env_path() -> str:
    return str(Path(__file__).resolve().parents[2] / ".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class TraceForgeSettings:
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str
    traceforge_api_url: str
    traceforge_db_path: str
    zulip_url: str
    zulip_email: str
    zulip_api_key: str
    zulip_bot_name: str
    zulip_verify_ssl: bool
    zulip_poll_interval_seconds: float
    zulip_progress_enabled: bool = True
    zulip_reactions_enabled: bool = True
    agent_max_model_turns: int = 8
    agent_max_tool_calls: int = 12

    @property
    def llm_enabled(self) -> bool:
        return bool(self.deepseek_api_key)


def get_settings() -> TraceForgeSettings:
    load_env_file()
    return TraceForgeSettings(
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        traceforge_api_url=os.environ.get("TRACEFORGE_API_URL", "http://127.0.0.1:19090"),
        traceforge_db_path=os.environ.get(
            "TRACEFORGE_DB_PATH",
            str(Path(__file__).resolve().parents[2] / ".traceforge" / "traceforge.sqlite3"),
        ),
        zulip_url=first_env("TRACEFORGE_ZULIP_URL", "ZULIP_URL", default="https://127.0.0.1:18443"),
        zulip_email=first_env(
            "TRACEFORGE_ZULIP_EMAIL", "ZULIP_EMAIL", default="Jarvis-bot@traceforge.local"
        ),
        zulip_api_key=first_env("TRACEFORGE_ZULIP_API_KEY", "ZULIP_API_KEY"),
        zulip_bot_name=first_env("TRACEFORGE_ZULIP_BOT_NAME", "ZULIP_BOT_NAME", default="Jarvis"),
        zulip_verify_ssl=env_bool("TRACEFORGE_ZULIP_VERIFY_SSL", env_bool("ZULIP_VERIFY_SSL", False)),
        zulip_poll_interval_seconds=float(
            first_env("TRACEFORGE_ZULIP_POLL_INTERVAL_SECONDS", "ZULIP_POLL_INTERVAL_SECONDS", default="1.0")
        ),
        zulip_progress_enabled=env_bool("TRACEFORGE_ZULIP_PROGRESS_ENABLED", True),
        zulip_reactions_enabled=env_bool("TRACEFORGE_ZULIP_REACTIONS_ENABLED", True),
        agent_max_model_turns=int(os.environ.get("TRACEFORGE_AGENT_MAX_MODEL_TURNS", "8")),
        agent_max_tool_calls=int(os.environ.get("TRACEFORGE_AGENT_MAX_TOOL_CALLS", "12")),
    )
