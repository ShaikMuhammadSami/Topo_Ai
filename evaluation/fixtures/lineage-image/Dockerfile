FROM alpine:3.22

ARG SOURCE_REPOSITORY
ARG SOURCE_REVISION
ARG GITHUB_RUN_ID
ARG GITHUB_RUN_ATTEMPT
ARG GITHUB_WORKFLOW_REF

COPY --chown=65532:65532 run.sh runtime-mode.txt /opt/topo/

RUN set -eu; \
    printf '%s\n' \
      "fixture=topo-lineage-provider" \
      "repository=${SOURCE_REPOSITORY}" \
      "commit_sha=${SOURCE_REVISION}" \
      "github_run_id=${GITHUB_RUN_ID}" \
      "github_run_attempt=${GITHUB_RUN_ATTEMPT}" \
      "github_workflow_ref=${GITHUB_WORKFLOW_REF}" \
      > /topo-lineage-provider.txt; \
    chmod 0444 /topo-lineage-provider.txt /opt/topo/runtime-mode.txt; \
    chmod 0555 /opt/topo/run.sh

USER 65532:65532

ENTRYPOINT ["/opt/topo/run.sh"]
