FROM python:3.12-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt

COPY backend/ .
COPY migrations/ /migrations/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
