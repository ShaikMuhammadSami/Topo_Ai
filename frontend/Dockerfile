# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS base

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /opt/topo-frontend

FROM base AS dependencies

COPY package.json package-lock.json ./

RUN npm ci

FROM base AS builder

COPY --from=dependencies /opt/topo-frontend/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production

RUN npm run build

FROM base AS runtime

ARG OCI_SOURCE=""
ARG OCI_REVISION=""
ARG OCI_CREATED=""
ARG OCI_VERSION=""

LABEL org.opencontainers.image.title="TopoAI Frontend" \
      org.opencontainers.image.description="TopoAI same-origin browser product" \
      org.opencontainers.image.source="${OCI_SOURCE}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.vendor="TopoAI" \
      topo.component="frontend"

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN groupadd \
      --system \
      --gid 10001 \
      topo-frontend \
    && useradd \
      --system \
      --uid 10001 \
      --gid 10001 \
      --home-dir /nonexistent \
      --no-create-home \
      --shell /usr/sbin/nologin \
      topo-frontend

COPY --from=builder --chown=10001:10001 /opt/topo-frontend/public ./public
COPY --from=builder --chown=10001:10001 /opt/topo-frontend/.next/standalone ./
COPY --from=builder --chown=10001:10001 /opt/topo-frontend/.next/static ./.next/static

USER 10001:10001

EXPOSE 3000

STOPSIGNAL SIGTERM

ENTRYPOINT ["node"]
CMD ["server.js"]
