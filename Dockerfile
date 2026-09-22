FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BGC_CONFIG_DIR=/config \
    BGC_IMPORT_DIR=/data/import \
    BGC_MANUALS_DIR=/data/manuals

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

RUN mkdir -p /config /data/import /data/manuals

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)"

CMD ["uvicorn", "boardgamecompanion.main:app", "--host", "0.0.0.0", "--port", "8787"]
