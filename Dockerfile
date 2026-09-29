FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin cryptoforge

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY user_data/strategies ./user_data/strategies
COPY docker ./docker

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -e . \
    && chmod +x /app/docker/*.sh

RUN mkdir -p /app/data /app/logs /app/outbox \
    && chown -R cryptoforge:cryptoforge /app

USER cryptoforge

ENV PYTHONPATH=/app/src \
    CRYPTOFORGE_DATA_DIR=/app/data \
    CRYPTOFORGE_OUTBOX_DB=/app/data/outbox.sqlite3 \
    CRYPTOFORGE_TELEGRAM_RELAY_STATE=/app/data/telegram-relay-state.json

ENTRYPOINT ["/app/docker/entrypoint.sh"]
