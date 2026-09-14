# syntax=docker/dockerfile:1.7

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG OCI_SOURCE=""
ARG OCI_REVISION=""
ARG OCI_CREATED=""
ARG OCI_VERSION=""

LABEL org.opencontainers.image.title="Topo Agent" \
      org.opencontainers.image.description="TopoAI Kubernetes observer and runtime agent" \
      org.opencontainers.image.source="${OCI_SOURCE}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.vendor="TopoAI" \
      topo.component="observer"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/topo-agent/src \
    TOPO_AGENT_HOME=/var/lib/topo-agent

RUN groupadd \
      --system \
      --gid 10001 \
      topo-agent \
    && useradd \
      --system \
      --uid 10001 \
      --gid 10001 \
      --home-dir /var/lib/topo-agent \
      --no-create-home \
      --shell /usr/sbin/nologin \
      topo-agent

WORKDIR /opt/topo-agent

COPY requirements.lock ./requirements.lock

RUN python -m pip install \
      --no-cache-dir \
      --no-deps \
      --requirement requirements.lock \
    && python -m pip check

COPY src ./src

RUN mkdir -p \
      /var/lib/topo-agent \
    && chown \
      topo-agent:topo-agent \
      /var/lib/topo-agent

USER 10001:10001

STOPSIGNAL SIGTERM

ENTRYPOINT ["python", "-m", "topo_agent"]

CMD ["run"]
