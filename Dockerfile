FROM docker.io/library/python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir "starlette>=0.37" "uvicorn>=0.30" "fastembed>=0.5"

COPY src ./src
COPY workspace ./workspace

ENV PYTHONPATH=/app/src
ENV TRACEFORGE_MEMORY_EMBEDDING_PROVIDER=local
ENV TRACEFORGE_MEMORY_EMBEDDING_CACHE_DIR=/data/models/embeddings

EXPOSE 8090

CMD ["uvicorn", "traceforge.server:app", "--host", "0.0.0.0", "--port", "8090"]
