# syntax=docker/dockerfile:1.7
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG OCI_SOURCE="unknown"
ARG OCI_REVISION="unknown"
ARG OCI_CREATED="1970-01-01T00:00:00Z"
ARG OCI_VERSION="unknown"

LABEL org.opencontainers.image.title="TopoAI Backend" \
      org.opencontainers.image.description="Evidence-based infrastructure intelligence API" \
      org.opencontainers.image.source="${OCI_SOURCE}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.version="${OCI_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 topo \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent topo

WORKDIR /opt/topo

COPY requirements.lock ./requirements.lock

RUN python -m pip install --no-cache-dir --no-deps --requirement requirements.lock \
    && python -m pip check

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY app ./app

RUN mkdir -p /opt/topo/data \
    && chown 10001:10001 /opt/topo/data

USER 10001:10001

EXPOSE 8000

STOPSIGNAL SIGTERM

ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
