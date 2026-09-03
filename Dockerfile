FROM docker.io/library/python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir "starlette>=0.37" "uvicorn>=0.30" "fastembed>=0.5" "mcp>=1.0" \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g tavily-mcp@latest \
    && rm -rf /var/lib/apt/lists/*

COPY src ./src
COPY workspace ./workspace
COPY workspace-gitea-audit ./workspace-gitea-audit
COPY workspace_shared ./workspace_shared
COPY agents.yaml ./agents.yaml

ENV PYTHONPATH=/app/src
ENV TRACEFORGE_MEMORY_EMBEDDING_PROVIDER=local
ENV TRACEFORGE_MEMORY_EMBEDDING_CACHE_DIR=/data/models/embeddings

EXPOSE 8090

CMD ["uvicorn", "traceforge.server:app", "--host", "0.0.0.0", "--port", "8090"]
