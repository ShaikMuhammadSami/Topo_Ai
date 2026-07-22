FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TOPO_AGENT_HOME=/var/lib/topo-agent

RUN groupadd \
      --gid 10001 \
      topo-agent \
    && useradd \
      --uid 10001 \
      --gid 10001 \
      --create-home \
      topo-agent

WORKDIR /opt/topo-agent

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install \
      --no-cache-dir \
      .

RUN mkdir -p \
      /var/lib/topo-agent \
    && chown -R \
      topo-agent:topo-agent \
      /var/lib/topo-agent

USER 10001:10001

ENTRYPOINT ["topo-agent"]

CMD ["run"]