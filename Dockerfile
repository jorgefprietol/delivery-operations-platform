FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS builder
WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock

FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9
ARG SOURCE_REVISION=development
LABEL org.opencontainers.image.title="Delivery Operations Platform" \
      org.opencontainers.image.source="https://github.com/jorgefprietol/delivery-operations-platform" \
      org.opencontainers.image.revision=$SOURCE_REVISION \
      org.opencontainers.image.licenses="MIT"
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SOURCE_REVISION=$SOURCE_REVISION DATABASE_PATH=/data/delivery.db XDG_CACHE_HOME=/tmp/cache XDG_DATA_HOME=/tmp/data
RUN groupadd --gid 10001 delivery && useradd --uid 10001 --gid 10001 --no-create-home delivery && mkdir /data && chown delivery:delivery /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=delivery:delivery delivery ./delivery
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=6 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=2)"]
CMD ["python", "-m", "delivery"]
