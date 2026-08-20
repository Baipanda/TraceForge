FROM docker.io/library/python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir "starlette>=0.37" "uvicorn>=0.30"

COPY src ./src
COPY workspace ./workspace

ENV PYTHONPATH=/app/src

EXPOSE 8090

CMD ["uvicorn", "traceforge.server:app", "--host", "0.0.0.0", "--port", "8090"]
