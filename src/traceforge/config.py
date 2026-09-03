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
    zulip_api_connect_url: str | None = None
    zulip_progress_enabled: bool = True
    zulip_reactions_enabled: bool = True
    agent_max_model_turns: int = 8
    agent_max_tool_calls: int = 12
    memory_search_mode: str = "hybrid"
    memory_embedding_enabled: bool = True
    memory_embedding_provider: str = "auto"
    memory_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    memory_embedding_cache_dir: str = ""
    memory_embedding_fallback: str = "none"
    memory_embedding_api_key: str | None = None
    memory_embedding_base_url: str = ""
    memory_hybrid_fts_weight: float = 0.5
    session_keep_recent_tokens: int = 20_000
    gitea_webhook_secret: str = ""
    repoaudit_zulip_email: str = ""
    repoaudit_zulip_api_key: str = ""
    repoaudit_notify_stream: str = "general"
    repoaudit_notify_topic: str = "gitea"
    gitea_url: str = "http://127.0.0.1:13000"
    gitea_api_connect_url: str | None = None
    gitea_token: str = ""
    agents_config_path: str = ""

    @property
    def llm_enabled(self) -> bool:
        return bool(self.deepseek_api_key)


def get_settings() -> TraceForgeSettings:
    load_env_file()
    db_path = os.environ.get(
        "TRACEFORGE_DB_PATH",
        str(Path(__file__).resolve().parents[2] / ".traceforge" / "traceforge.sqlite3"),
    )
    cache_dir = os.environ.get("TRACEFORGE_MEMORY_EMBEDDING_CACHE_DIR", "")
    if not cache_dir:
        cache_dir = str(Path(db_path).expanduser().resolve().parent / "models" / "embeddings")
    return TraceForgeSettings(
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        traceforge_api_url=os.environ.get("TRACEFORGE_API_URL", "http://127.0.0.1:19090"),
        traceforge_db_path=db_path,
        zulip_url=first_env("TRACEFORGE_ZULIP_URL", "ZULIP_URL", default="https://127.0.0.1:18443"),
        zulip_api_connect_url=first_env("TRACEFORGE_ZULIP_API_CONNECT_URL", "ZULIP_API_CONNECT_URL")
        or None,
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
        memory_search_mode=os.environ.get("TRACEFORGE_MEMORY_SEARCH_MODE", "hybrid"),
        memory_embedding_enabled=env_bool("TRACEFORGE_MEMORY_EMBEDDING_ENABLED", True),
        memory_embedding_provider=os.environ.get("TRACEFORGE_MEMORY_EMBEDDING_PROVIDER", "auto"),
        memory_embedding_model=os.environ.get(
            "TRACEFORGE_MEMORY_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
        ),
        memory_embedding_cache_dir=cache_dir,
        memory_embedding_fallback=os.environ.get("TRACEFORGE_MEMORY_EMBEDDING_FALLBACK", "none"),
        memory_embedding_api_key=os.environ.get("TRACEFORGE_MEMORY_EMBEDDING_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or None,
        memory_embedding_base_url=os.environ.get(
            "TRACEFORGE_MEMORY_EMBEDDING_BASE_URL",
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ),
        memory_hybrid_fts_weight=float(os.environ.get("TRACEFORGE_MEMORY_HYBRID_FTS_WEIGHT", "0.5")),
        session_keep_recent_tokens=int(
            os.environ.get("TRACEFORGE_SESSION_KEEP_RECENT_TOKENS", "20000")
        ),
        gitea_webhook_secret=first_env(
            "TRACEFORGE_GITEA_WEBHOOK_SECRET", "GITEA_WEBHOOK_SECRET", default=""
        ),
        repoaudit_zulip_email=first_env(
            "TRACEFORGE_REPOAUDIT_ZULIP_EMAIL",
            "REPOAUDIT_ZULIP_EMAIL",
            default="RepoAudit-bot@traceforge.local",
        ),
        repoaudit_zulip_api_key=first_env(
            "TRACEFORGE_REPOAUDIT_ZULIP_API_KEY", "REPOAUDIT_ZULIP_API_KEY", default=""
        ),
        repoaudit_notify_stream=first_env(
            "TRACEFORGE_REPOAUDIT_NOTIFY_STREAM",
            "REPOAUDIT_NOTIFY_STREAM",
            default="general",
        ),
        repoaudit_notify_topic=first_env(
            "TRACEFORGE_REPOAUDIT_NOTIFY_TOPIC",
            "REPOAUDIT_NOTIFY_TOPIC",
            default="gitea",
        ),
        gitea_url=first_env(
            "TRACEFORGE_GITEA_URL", "GITEA_URL", default="http://127.0.0.1:13000"
        ),
        gitea_api_connect_url=first_env(
            "TRACEFORGE_GITEA_API_CONNECT_URL", "GITEA_API_CONNECT_URL"
        )
        or None,
        gitea_token=first_env("TRACEFORGE_GITEA_TOKEN", "GITEA_TOKEN", default=""),
        agents_config_path=first_env(
            "TRACEFORGE_AGENTS_CONFIG", "AGENTS_CONFIG", default=""
        ),
    )
