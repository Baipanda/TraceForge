"""Download and warm up the local embedding model (OpenClaw-style offline setup)."""

from __future__ import annotations

import argparse
import sys

from traceforge.config import get_settings
from traceforge.memory.embeddings import LocalEmbeddingProvider, build_embedding_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download TraceForge local embedding model into cache.")
    parser.add_argument(
        "--model",
        default=None,
        help="Override TRACEFORGE_MEMORY_EMBEDDING_MODEL (default from settings)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Override TRACEFORGE_MEMORY_EMBEDDING_CACHE_DIR",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    model = args.model or settings.memory_embedding_model
    cache_dir = args.cache_dir or settings.memory_embedding_cache_dir or None

    provider = build_embedding_provider(
        enabled=True,
        provider="local",
        api_key=None,
        base_url="",
        model=model,
        cache_dir=cache_dir,
    )
    if provider is None or not isinstance(provider, LocalEmbeddingProvider):
        print("Local embedding provider is not available. Install: pip install -e '.[memory]'", file=sys.stderr)
        return 1

    print(f"Downloading / loading embedding model: {model}")
    if cache_dir:
        print(f"Cache dir: {cache_dir}")
    try:
        vectors = provider.embed(["TraceForge embedding warmup", "记忆检索预热"])
    except ImportError as exc:
        print(
            "缺少 fastembed。请先安装：pip install 'fastembed>=0.5' 或 pip install -e '.[memory]'",
            file=sys.stderr,
        )
        print(f"详情: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        message = str(exc)
        if "ConnectError" in type(exc).__name__ or "Network is unreachable" in message:
            print(
                "无法从 HuggingFace 下载模型。若在国内，可先试镜像：",
                file=sys.stderr,
            )
            print(
                "  ./scripts/download_embedding.sh",
                file=sys.stderr,
            )
            print(
                "  或: HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 ./scripts/download_embedding.sh",
                file=sys.stderr,
            )
            print(
                "或检查本机网络/代理；有网后在 Docker 内：",
                file=sys.stderr,
            )
            print(
                "  docker exec traceforge-app python -m traceforge.memory.download_embedding",
                file=sys.stderr,
            )
            print(f"目标 cache: {cache_dir or '(fastembed 默认缓存)'}", file=sys.stderr)
        else:
            print(f"下载/加载失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Ready. dims={len(vectors[0])}, model={provider.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
