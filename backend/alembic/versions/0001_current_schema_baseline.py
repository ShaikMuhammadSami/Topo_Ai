"""current schema baseline

Revision ID: 0001_current_schema
Revises:
Create Date: 2026-08-28

The schema specification in this revision is frozen. It intentionally does
not import application models, so future ORM changes cannot alter historical
migration behavior.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_current_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SCHEMA = json.loads(
    r"""
{
  "tables": [
    {
      "columns": [
        {
          "name": "event_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "sequence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "approval_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "action_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "event_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "from_status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "to_status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "actor_subject",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "actor_display_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "actor_roles_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "authentication_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "occurred_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "action_id"
          ],
          "name": "ix_action_approval_events_action_id",
          "unique": false
        },
        {
          "columns": [
            "actor_subject"
          ],
          "name": "ix_action_approval_events_actor_subject",
          "unique": false
        },
        {
          "columns": [
            "approval_id"
          ],
          "name": "ix_action_approval_events_approval_id",
          "unique": false
        },
        {
          "columns": [
            "event_type"
          ],
          "name": "ix_action_approval_events_event_type",
          "unique": false
        },
        {
          "columns": [
            "evidence_fingerprint"
          ],
          "name": "ix_action_approval_events_evidence_fingerprint",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_action_approval_events_incident_id",
          "unique": false
        },
        {
          "columns": [
            "occurred_at"
          ],
          "name": "ix_action_approval_events_occurred_at",
          "unique": false
        },
        {
          "columns": [
            "to_status"
          ],
          "name": "ix_action_approval_events_to_status",
          "unique": false
        }
      ],
      "name": "action_approval_events",
      "unique_constraints": [
        {
          "columns": [
            "approval_id",
            "sequence"
          ],
          "name": "uq_action_approval_event_sequence"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "approval_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "action_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "action_family",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "risk",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "requires_human_approval",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "boolean"
          }
        },
        {
          "name": "policy_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "readiness_status_at_request",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "evidence_fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "target_entity_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "target_change_event_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "readiness_snapshot_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "pending_key",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "request_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "requested_by_subject",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "requested_by_display_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "requested_by_roles_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "requested_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "decided_by_subject",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "decided_by_display_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "decided_by_roles_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "decided_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "decision_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "expires_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "revoked_by_subject",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "revoked_by_display_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "revoked_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "revocation_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "invalidated_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "invalidation_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "action_family"
          ],
          "name": "ix_action_approvals_action_family",
          "unique": false
        },
        {
          "columns": [
            "action_id"
          ],
          "name": "ix_action_approvals_action_id",
          "unique": false
        },
        {
          "columns": [
            "decided_at"
          ],
          "name": "ix_action_approvals_decided_at",
          "unique": false
        },
        {
          "columns": [
            "decided_by_subject"
          ],
          "name": "ix_action_approvals_decided_by_subject",
          "unique": false
        },
        {
          "columns": [
            "evidence_fingerprint"
          ],
          "name": "ix_action_approvals_evidence_fingerprint",
          "unique": false
        },
        {
          "columns": [
            "expires_at"
          ],
          "name": "ix_action_approvals_expires_at",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_action_approvals_incident_id",
          "unique": false
        },
        {
          "columns": [
            "invalidated_at"
          ],
          "name": "ix_action_approvals_invalidated_at",
          "unique": false
        },
        {
          "columns": [
            "pending_key"
          ],
          "name": "ix_action_approvals_pending_key",
          "unique": true
        },
        {
          "columns": [
            "policy_version"
          ],
          "name": "ix_action_approvals_policy_version",
          "unique": false
        },
        {
          "columns": [
            "requested_at"
          ],
          "name": "ix_action_approvals_requested_at",
          "unique": false
        },
        {
          "columns": [
            "requested_by_subject"
          ],
          "name": "ix_action_approvals_requested_by_subject",
          "unique": false
        },
        {
          "columns": [
            "revoked_at"
          ],
          "name": "ix_action_approvals_revoked_at",
          "unique": false
        },
        {
          "columns": [
            "revoked_by_subject"
          ],
          "name": "ix_action_approvals_revoked_by_subject",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_action_approvals_status",
          "unique": false
        },
        {
          "columns": [
            "target_change_event_id"
          ],
          "name": "ix_action_approvals_target_change_event_id",
          "unique": false
        }
      ],
      "name": "action_approvals",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "enrollment_token_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "token_hash",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "token_hint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 32
          }
        },
        {
          "name": "label",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "max_uses",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "use_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "expires_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_used_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "revoked_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_by",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "expires_at"
          ],
          "name": "ix_agent_enrollment_tokens_expires_at",
          "unique": false
        },
        {
          "columns": [
            "token_hash"
          ],
          "name": "ix_agent_enrollment_tokens_token_hash",
          "unique": true
        }
      ],
      "name": "agent_enrollment_tokens",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "evidence_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "repository_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "repository",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "workflow_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "workflow_ref",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 2000
          }
        },
        {
          "name": "workflow_run_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "run_attempt",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "commit_sha",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 40
          }
        },
        {
          "name": "artifact_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "image_repository",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 2000
          }
        },
        {
          "name": "image_reference",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 3000
          }
        },
        {
          "name": "image_digest",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 71
          }
        },
        {
          "name": "immutable_image_ref",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 3000
          }
        },
        {
          "name": "provider_evidence_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 150
          }
        },
        {
          "name": "provider_evidence_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "provider_evidence_reference",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 3000
          }
        },
        {
          "name": "provider_evidence_digest",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 71
          }
        },
        {
          "name": "provider_build_record_digest",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 71
          }
        },
        {
          "name": "provider_builder_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 3000
          }
        },
        {
          "name": "provider_build_started_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "provider_build_finished_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "provider_run_updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "observed_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "temporal_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "completeness",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "artifact_type"
          ],
          "name": "ix_build_artifact_evidence_artifact_type",
          "unique": false
        },
        {
          "columns": [
            "commit_sha"
          ],
          "name": "ix_build_artifact_evidence_commit_sha",
          "unique": false
        },
        {
          "columns": [
            "completeness"
          ],
          "name": "ix_build_artifact_evidence_completeness",
          "unique": false
        },
        {
          "columns": [
            "image_digest"
          ],
          "name": "ix_build_artifact_evidence_image_digest",
          "unique": false
        },
        {
          "columns": [
            "image_repository"
          ],
          "name": "ix_build_artifact_evidence_image_repository",
          "unique": false
        },
        {
          "columns": [
            "observed_at"
          ],
          "name": "ix_build_artifact_evidence_observed_at",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_build_artifact_evidence_provider",
          "unique": false
        },
        {
          "columns": [
            "provider_evidence_id"
          ],
          "name": "ix_build_artifact_evidence_provider_evidence_id",
          "unique": false
        },
        {
          "columns": [
            "provider_evidence_type"
          ],
          "name": "ix_build_artifact_evidence_provider_evidence_type",
          "unique": false
        },
        {
          "columns": [
            "provider_run_updated_at"
          ],
          "name": "ix_build_artifact_evidence_provider_run_updated_at",
          "unique": false
        },
        {
          "columns": [
            "repository"
          ],
          "name": "ix_build_artifact_evidence_repository",
          "unique": false
        },
        {
          "columns": [
            "repository_id"
          ],
          "name": "ix_build_artifact_evidence_repository_id",
          "unique": false
        },
        {
          "columns": [
            "run_attempt"
          ],
          "name": "ix_build_artifact_evidence_run_attempt",
          "unique": false
        },
        {
          "columns": [
            "workflow_id"
          ],
          "name": "ix_build_artifact_evidence_workflow_id",
          "unique": false
        },
        {
          "columns": [
            "workflow_run_id"
          ],
          "name": "ix_build_artifact_evidence_workflow_run_id",
          "unique": false
        }
      ],
      "name": "build_artifact_evidence",
      "unique_constraints": [
        {
          "columns": [
            "provider",
            "repository_id",
            "workflow_run_id",
            "run_attempt",
            "image_digest",
            "provider_evidence_id"
          ],
          "name": "uq_build_artifact_provider_fact"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "analysis_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "generated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "algorithm_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "candidate_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "hypothesis_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "top_hypothesis_score",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "float"
          }
        },
        {
          "name": "top_root_event_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "generated_at"
          ],
          "name": "ix_causal_analyses_generated_at",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_causal_analyses_incident_id",
          "unique": false
        },
        {
          "columns": [
            "top_hypothesis_score"
          ],
          "name": "ix_causal_analyses_top_hypothesis_score",
          "unique": false
        },
        {
          "columns": [
            "top_root_event_id"
          ],
          "name": "ix_causal_analyses_top_root_event_id",
          "unique": false
        }
      ],
      "name": "causal_analyses",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "link_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "event_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "entity_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "link_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "confidence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "float"
          }
        },
        {
          "name": "reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "snapshot_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "entity_id"
          ],
          "name": "ix_change_entity_links_entity_id",
          "unique": false
        },
        {
          "columns": [
            "event_id"
          ],
          "name": "ix_change_entity_links_event_id",
          "unique": false
        },
        {
          "columns": [
            "link_type"
          ],
          "name": "ix_change_entity_links_link_type",
          "unique": false
        },
        {
          "columns": [
            "snapshot_id"
          ],
          "name": "ix_change_entity_links_snapshot_id",
          "unique": false
        }
      ],
      "name": "change_entity_links",
      "unique_constraints": [
        {
          "columns": [
            "event_id",
            "entity_id",
            "link_type"
          ],
          "name": "uq_change_event_entity_link"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "event_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "event_fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 128
          }
        },
        {
          "name": "source",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "kind",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "external_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "origin_change_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "summary",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "actor",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "occurred_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "received_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "environment",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "provider",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "account_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "region",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "cluster_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "repository",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "commit_sha",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "pipeline_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "release_version",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "terraform_workspace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "risk_score",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "risk_level",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "observation_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "metadata_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "raw_payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "agent_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "account_id"
          ],
          "name": "ix_change_events_account_id",
          "unique": false
        },
        {
          "columns": [
            "actor"
          ],
          "name": "ix_change_events_actor",
          "unique": false
        },
        {
          "columns": [
            "agent_id"
          ],
          "name": "ix_change_events_agent_id",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_change_events_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "commit_sha"
          ],
          "name": "ix_change_events_commit_sha",
          "unique": false
        },
        {
          "columns": [
            "environment"
          ],
          "name": "ix_change_events_environment",
          "unique": false
        },
        {
          "columns": [
            "event_fingerprint"
          ],
          "name": "ix_change_events_event_fingerprint",
          "unique": true
        },
        {
          "columns": [
            "external_id"
          ],
          "name": "ix_change_events_external_id",
          "unique": false
        },
        {
          "columns": [
            "kind"
          ],
          "name": "ix_change_events_kind",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_change_events_namespace",
          "unique": false
        },
        {
          "columns": [
            "occurred_at"
          ],
          "name": "ix_change_events_occurred_at",
          "unique": false
        },
        {
          "columns": [
            "origin_change_id"
          ],
          "name": "ix_change_events_origin_change_id",
          "unique": false
        },
        {
          "columns": [
            "pipeline_name"
          ],
          "name": "ix_change_events_pipeline_name",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_change_events_provider",
          "unique": false
        },
        {
          "columns": [
            "received_at"
          ],
          "name": "ix_change_events_received_at",
          "unique": false
        },
        {
          "columns": [
            "region"
          ],
          "name": "ix_change_events_region",
          "unique": false
        },
        {
          "columns": [
            "release_version"
          ],
          "name": "ix_change_events_release_version",
          "unique": false
        },
        {
          "columns": [
            "repository"
          ],
          "name": "ix_change_events_repository",
          "unique": false
        },
        {
          "columns": [
            "risk_level"
          ],
          "name": "ix_change_events_risk_level",
          "unique": false
        },
        {
          "columns": [
            "risk_score"
          ],
          "name": "ix_change_events_risk_score",
          "unique": false
        },
        {
          "columns": [
            "source"
          ],
          "name": "ix_change_events_source",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_change_events_status",
          "unique": false
        },
        {
          "columns": [
            "terraform_workspace"
          ],
          "name": "ix_change_events_terraform_workspace",
          "unique": false
        }
      ],
      "name": "change_events",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "dead_letter_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "delivery_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "event_type",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "reason",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "attempt_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_attempt_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "replayed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "delivery_id"
          ],
          "name": "ix_change_source_dead_letters_delivery_id",
          "unique": false
        },
        {
          "columns": [
            "source_id"
          ],
          "name": "ix_change_source_dead_letters_source_id",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_change_source_dead_letters_status",
          "unique": false
        }
      ],
      "name": "change_source_dead_letters",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "delivery_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "delivery_key",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 128
          }
        },
        {
          "name": "source_delivery_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "event_type",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "payload_sha256",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "headers_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "event_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "error",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "received_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "processed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "delivery_key"
          ],
          "name": "ix_change_source_deliveries_delivery_key",
          "unique": true
        },
        {
          "columns": [
            "event_type"
          ],
          "name": "ix_change_source_deliveries_event_type",
          "unique": false
        },
        {
          "columns": [
            "payload_sha256"
          ],
          "name": "ix_change_source_deliveries_payload_sha256",
          "unique": false
        },
        {
          "columns": [
            "received_at"
          ],
          "name": "ix_change_source_deliveries_received_at",
          "unique": false
        },
        {
          "columns": [
            "source_delivery_id"
          ],
          "name": "ix_change_source_deliveries_source_delivery_id",
          "unique": false
        },
        {
          "columns": [
            "source_id"
          ],
          "name": "ix_change_source_deliveries_source_id",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_change_source_deliveries_status",
          "unique": false
        }
      ],
      "name": "change_source_deliveries",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "source_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "enabled",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "boolean"
          }
        },
        {
          "name": "secret_ref",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "config_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "filters_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "delivery_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "failure_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "last_event_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_success_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_error_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_error",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "enabled"
          ],
          "name": "ix_change_sources_enabled",
          "unique": false
        },
        {
          "columns": [
            "name"
          ],
          "name": "ix_change_sources_name",
          "unique": false
        },
        {
          "columns": [
            "source_type"
          ],
          "name": "ix_change_sources_source_type",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_change_sources_status",
          "unique": false
        }
      ],
      "name": "change_sources",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "change_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "change_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "category",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "importance",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "source_system",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "summary",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "detected_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "from_snapshot_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "to_snapshot_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "entity_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "entity_kind",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "entity_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "relationship_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "relationship_type",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "category"
          ],
          "name": "ix_changes_category",
          "unique": false
        },
        {
          "columns": [
            "change_type"
          ],
          "name": "ix_changes_change_type",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_changes_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "detected_at"
          ],
          "name": "ix_changes_detected_at",
          "unique": false
        },
        {
          "columns": [
            "entity_id"
          ],
          "name": "ix_changes_entity_id",
          "unique": false
        },
        {
          "columns": [
            "entity_kind"
          ],
          "name": "ix_changes_entity_kind",
          "unique": false
        },
        {
          "columns": [
            "fingerprint"
          ],
          "name": "ix_changes_fingerprint",
          "unique": false
        },
        {
          "columns": [
            "from_snapshot_id"
          ],
          "name": "ix_changes_from_snapshot_id",
          "unique": false
        },
        {
          "columns": [
            "importance"
          ],
          "name": "ix_changes_importance",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_changes_namespace",
          "unique": false
        },
        {
          "columns": [
            "relationship_id"
          ],
          "name": "ix_changes_relationship_id",
          "unique": false
        },
        {
          "columns": [
            "to_snapshot_id"
          ],
          "name": "ix_changes_to_snapshot_id",
          "unique": false
        }
      ],
      "name": "changes",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "cloud_account_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "account_number",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "display_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "principal_arn",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "metadata_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "last_seen_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "account_number"
          ],
          "name": "ix_cloud_accounts_account_number",
          "unique": false
        },
        {
          "columns": [
            "last_seen_at"
          ],
          "name": "ix_cloud_accounts_last_seen_at",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_cloud_accounts_provider",
          "unique": false
        }
      ],
      "name": "cloud_accounts",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "cloud_resource_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "account_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "region",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "resource_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "resource_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "arn",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 2000
          }
        },
        {
          "name": "name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "vpc_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "subnet_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "tags_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "properties_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "observed_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "agent_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "account_id"
          ],
          "name": "ix_cloud_resources_account_id",
          "unique": false
        },
        {
          "columns": [
            "agent_id"
          ],
          "name": "ix_cloud_resources_agent_id",
          "unique": false
        },
        {
          "columns": [
            "arn"
          ],
          "name": "ix_cloud_resources_arn",
          "unique": false
        },
        {
          "columns": [
            "name"
          ],
          "name": "ix_cloud_resources_name",
          "unique": false
        },
        {
          "columns": [
            "observed_at"
          ],
          "name": "ix_cloud_resources_observed_at",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_cloud_resources_provider",
          "unique": false
        },
        {
          "columns": [
            "region"
          ],
          "name": "ix_cloud_resources_region",
          "unique": false
        },
        {
          "columns": [
            "resource_id"
          ],
          "name": "ix_cloud_resources_resource_id",
          "unique": false
        },
        {
          "columns": [
            "resource_type"
          ],
          "name": "ix_cloud_resources_resource_type",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_cloud_resources_status",
          "unique": false
        },
        {
          "columns": [
            "vpc_id"
          ],
          "name": "ix_cloud_resources_vpc_id",
          "unique": false
        }
      ],
      "name": "cloud_resources",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "event_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "sequence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "execution_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "approval_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "action_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "event_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "from_status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "to_status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "actor_subject",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "actor_display_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "actor_roles_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "authentication_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "claim_generation",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "occurred_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "action_id"
          ],
          "name": "ix_execution_intent_events_action_id",
          "unique": false
        },
        {
          "columns": [
            "actor_subject"
          ],
          "name": "ix_execution_intent_events_actor_subject",
          "unique": false
        },
        {
          "columns": [
            "approval_id"
          ],
          "name": "ix_execution_intent_events_approval_id",
          "unique": false
        },
        {
          "columns": [
            "event_type"
          ],
          "name": "ix_execution_intent_events_event_type",
          "unique": false
        },
        {
          "columns": [
            "execution_id"
          ],
          "name": "ix_execution_intent_events_execution_id",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_execution_intent_events_incident_id",
          "unique": false
        },
        {
          "columns": [
            "occurred_at"
          ],
          "name": "ix_execution_intent_events_occurred_at",
          "unique": false
        },
        {
          "columns": [
            "to_status"
          ],
          "name": "ix_execution_intent_events_to_status",
          "unique": false
        }
      ],
      "name": "execution_intent_events",
      "unique_constraints": [
        {
          "columns": [
            "execution_id",
            "sequence"
          ],
          "name": "uq_execution_intent_event_sequence"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "execution_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "approval_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "action_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "action_family",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "approval_evidence_fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "policy_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "risk",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "target_entity_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "target_change_event_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "execution_snapshot_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "idempotency_key",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "created_by_subject",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "created_by_display_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "created_by_roles_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_by_authentication_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "claimed_by_subject",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "claimed_by_display_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "claimed_by_authentication_type",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "claimed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "claim_expires_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "claim_token_hash",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "claim_generation",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "attempt_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "cancelled_by_subject",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "cancelled_by_display_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "cancelled_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "cancellation_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "invalidated_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "invalidation_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "expired_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "expiration_reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "started_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "completed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "failed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_error_code",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "last_error_message",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "result_reference",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "execution_performed",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "boolean"
          }
        },
        {
          "name": "row_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "action_family"
          ],
          "name": "ix_execution_intents_action_family",
          "unique": false
        },
        {
          "columns": [
            "action_id"
          ],
          "name": "ix_execution_intents_action_id",
          "unique": false
        },
        {
          "columns": [
            "approval_evidence_fingerprint"
          ],
          "name": "ix_execution_intents_approval_evidence_fingerprint",
          "unique": false
        },
        {
          "columns": [
            "approval_id"
          ],
          "name": "ix_execution_intents_approval_id",
          "unique": true
        },
        {
          "columns": [
            "cancelled_at"
          ],
          "name": "ix_execution_intents_cancelled_at",
          "unique": false
        },
        {
          "columns": [
            "cancelled_by_subject"
          ],
          "name": "ix_execution_intents_cancelled_by_subject",
          "unique": false
        },
        {
          "columns": [
            "claim_expires_at"
          ],
          "name": "ix_execution_intents_claim_expires_at",
          "unique": false
        },
        {
          "columns": [
            "claimed_at"
          ],
          "name": "ix_execution_intents_claimed_at",
          "unique": false
        },
        {
          "columns": [
            "claimed_by_subject"
          ],
          "name": "ix_execution_intents_claimed_by_subject",
          "unique": false
        },
        {
          "columns": [
            "created_at"
          ],
          "name": "ix_execution_intents_created_at",
          "unique": false
        },
        {
          "columns": [
            "created_by_subject"
          ],
          "name": "ix_execution_intents_created_by_subject",
          "unique": false
        },
        {
          "columns": [
            "expired_at"
          ],
          "name": "ix_execution_intents_expired_at",
          "unique": false
        },
        {
          "columns": [
            "idempotency_key"
          ],
          "name": "ix_execution_intents_idempotency_key",
          "unique": true
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_execution_intents_incident_id",
          "unique": false
        },
        {
          "columns": [
            "invalidated_at"
          ],
          "name": "ix_execution_intents_invalidated_at",
          "unique": false
        },
        {
          "columns": [
            "policy_version"
          ],
          "name": "ix_execution_intents_policy_version",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_execution_intents_status",
          "unique": false
        },
        {
          "columns": [
            "target_change_event_id"
          ],
          "name": "ix_execution_intents_target_change_event_id",
          "unique": false
        }
      ],
      "name": "execution_intents",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "override_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "entity_kind",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "entity_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "action",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "canonical_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "reason",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "active",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "boolean"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_identity_overrides_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_identity_overrides_namespace",
          "unique": false
        }
      ],
      "name": "identity_overrides",
      "unique_constraints": [
        {
          "columns": [
            "cluster_name",
            "namespace",
            "entity_kind",
            "entity_name"
          ],
          "name": "uq_identity_override_target"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "snapshot_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "generated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "identity_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "unresolved_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "excluded_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "generated_at"
          ],
          "name": "ix_identity_resolutions_generated_at",
          "unique": false
        }
      ],
      "name": "identity_resolutions",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "analysis_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "signal_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "topology_snapshot_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "algorithm_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "generated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "incident_title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "candidate_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "hypothesis_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "top_hypothesis_title",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "top_hypothesis_score",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_incident_analyses_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "generated_at"
          ],
          "name": "ix_incident_analyses_generated_at",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_incident_analyses_namespace",
          "unique": false
        },
        {
          "columns": [
            "signal_id"
          ],
          "name": "ix_incident_analyses_signal_id",
          "unique": false
        },
        {
          "columns": [
            "topology_snapshot_id"
          ],
          "name": "ix_incident_analyses_topology_snapshot_id",
          "unique": false
        }
      ],
      "name": "incident_analyses",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "message_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "session_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "role",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "content",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "provider",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "answer_status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "confidence",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "evidence_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "suggested_questions_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "warning",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_incident_copilot_messages_incident_id",
          "unique": false
        },
        {
          "columns": [
            "role"
          ],
          "name": "ix_incident_copilot_messages_role",
          "unique": false
        },
        {
          "columns": [
            "session_id"
          ],
          "name": "ix_incident_copilot_messages_session_id",
          "unique": false
        }
      ],
      "name": "incident_copilot_messages",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "session_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "model_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_incident_copilot_sessions_incident_id",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_incident_copilot_sessions_provider",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_incident_copilot_sessions_status",
          "unique": false
        }
      ],
      "name": "incident_copilot_sessions",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "explanation_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "topology_snapshot_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "analysis_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "model_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "prompt_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "grounding_hash",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "confidence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "generated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "warnings_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "analysis_id"
          ],
          "name": "ix_incident_explanations_analysis_id",
          "unique": false
        },
        {
          "columns": [
            "generated_at"
          ],
          "name": "ix_incident_explanations_generated_at",
          "unique": false
        },
        {
          "columns": [
            "grounding_hash"
          ],
          "name": "ix_incident_explanations_grounding_hash",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_incident_explanations_incident_id",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_incident_explanations_provider",
          "unique": false
        },
        {
          "columns": [
            "topology_snapshot_id"
          ],
          "name": "ix_incident_explanations_topology_snapshot_id",
          "unique": false
        }
      ],
      "name": "incident_explanations",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "plan_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "objective",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "incident_summary",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "model_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "prompt_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "grounding_hash",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "overall_confidence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "evidence_gaps_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "warnings_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "grounding_hash"
          ],
          "name": "ix_incident_investigation_plans_grounding_hash",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_incident_investigation_plans_incident_id",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_incident_investigation_plans_provider",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_incident_investigation_plans_status",
          "unique": false
        }
      ],
      "name": "incident_investigation_plans",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "step_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "plan_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "sequence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "objective",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "command_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "command",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "target",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "expected_observation",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "success_criteria",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "failure_indication",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "finding",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "responder_notes",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "completed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_incident_investigation_steps_incident_id",
          "unique": false
        },
        {
          "columns": [
            "plan_id"
          ],
          "name": "ix_incident_investigation_steps_plan_id",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_incident_investigation_steps_status",
          "unique": false
        }
      ],
      "name": "incident_investigation_steps",
      "unique_constraints": [
        {
          "columns": [
            "plan_id",
            "sequence"
          ],
          "name": "uq_investigation_plan_sequence"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "outcome_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "causal_analysis_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "response_plan_reference",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "rca_verdict",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "mitigated_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "resolved_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "source_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "causal_analysis_id"
          ],
          "name": "ix_incident_outcomes_causal_analysis_id",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_incident_outcomes_incident_id",
          "unique": true
        },
        {
          "columns": [
            "mitigated_at"
          ],
          "name": "ix_incident_outcomes_mitigated_at",
          "unique": false
        },
        {
          "columns": [
            "rca_verdict"
          ],
          "name": "ix_incident_outcomes_rca_verdict",
          "unique": false
        },
        {
          "columns": [
            "resolved_at"
          ],
          "name": "ix_incident_outcomes_resolved_at",
          "unique": false
        },
        {
          "columns": [
            "response_plan_reference"
          ],
          "name": "ix_incident_outcomes_response_plan_reference",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_incident_outcomes_status",
          "unique": false
        }
      ],
      "name": "incident_outcomes",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "severity",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "summary",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "primary_signal_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "latest_signal_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "topology_snapshot_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "affected_entity_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "affected_object_kind",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "affected_object_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "first_observed_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_observed_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "latest_analysis_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "top_hypothesis_title",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "top_hypothesis_score",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "recommendation_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "latest_recommendation_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "recovery_status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "latest_recovery_verification_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "occurrence_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "status_note",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "affected_entity_id"
          ],
          "name": "ix_incidents_affected_entity_id",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_incidents_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "fingerprint"
          ],
          "name": "ix_incidents_fingerprint",
          "unique": false
        },
        {
          "columns": [
            "first_observed_at"
          ],
          "name": "ix_incidents_first_observed_at",
          "unique": false
        },
        {
          "columns": [
            "last_observed_at"
          ],
          "name": "ix_incidents_last_observed_at",
          "unique": false
        },
        {
          "columns": [
            "latest_analysis_id"
          ],
          "name": "ix_incidents_latest_analysis_id",
          "unique": false
        },
        {
          "columns": [
            "latest_recommendation_id"
          ],
          "name": "ix_incidents_latest_recommendation_id",
          "unique": false
        },
        {
          "columns": [
            "latest_recovery_verification_id"
          ],
          "name": "ix_incidents_latest_recovery_verification_id",
          "unique": false
        },
        {
          "columns": [
            "latest_signal_id"
          ],
          "name": "ix_incidents_latest_signal_id",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_incidents_namespace",
          "unique": false
        },
        {
          "columns": [
            "primary_signal_id"
          ],
          "name": "ix_incidents_primary_signal_id",
          "unique": false
        },
        {
          "columns": [
            "recovery_status"
          ],
          "name": "ix_incidents_recovery_status",
          "unique": false
        },
        {
          "columns": [
            "severity"
          ],
          "name": "ix_incidents_severity",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_incidents_status",
          "unique": false
        },
        {
          "columns": [
            "topology_snapshot_id"
          ],
          "name": "ix_incidents_topology_snapshot_id",
          "unique": false
        }
      ],
      "name": "incidents",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "ownership_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "entity_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "service_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "cluster_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "entity_kind",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "entity_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "environment",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "owner_team",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "owner_email",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 320
          }
        },
        {
          "name": "oncall_contact",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "repository_url",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "business_capability",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "criticality",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "source",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "active",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "boolean"
          }
        },
        {
          "name": "notes",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "business_capability"
          ],
          "name": "ix_ownership_mappings_business_capability",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_ownership_mappings_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "criticality"
          ],
          "name": "ix_ownership_mappings_criticality",
          "unique": false
        },
        {
          "columns": [
            "entity_id"
          ],
          "name": "ix_ownership_mappings_entity_id",
          "unique": false
        },
        {
          "columns": [
            "entity_kind"
          ],
          "name": "ix_ownership_mappings_entity_kind",
          "unique": false
        },
        {
          "columns": [
            "entity_name"
          ],
          "name": "ix_ownership_mappings_entity_name",
          "unique": false
        },
        {
          "columns": [
            "environment"
          ],
          "name": "ix_ownership_mappings_environment",
          "unique": false
        },
        {
          "columns": [
            "fingerprint"
          ],
          "name": "ix_ownership_mappings_fingerprint",
          "unique": true
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_ownership_mappings_namespace",
          "unique": false
        },
        {
          "columns": [
            "owner_team"
          ],
          "name": "ix_ownership_mappings_owner_team",
          "unique": false
        },
        {
          "columns": [
            "service_name"
          ],
          "name": "ix_ownership_mappings_service_name",
          "unique": false
        }
      ],
      "name": "ownership_mappings",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "action_item_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "report_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "sequence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "description",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "owner_team",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "owner_contact",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "priority",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "due_date",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "success_criteria",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_ids_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "notes",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "completed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_post_incident_report_actions_incident_id",
          "unique": false
        },
        {
          "columns": [
            "owner_team"
          ],
          "name": "ix_post_incident_report_actions_owner_team",
          "unique": false
        },
        {
          "columns": [
            "priority"
          ],
          "name": "ix_post_incident_report_actions_priority",
          "unique": false
        },
        {
          "columns": [
            "report_id"
          ],
          "name": "ix_post_incident_report_actions_report_id",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_post_incident_report_actions_status",
          "unique": false
        }
      ],
      "name": "post_incident_report_actions",
      "unique_constraints": [
        {
          "columns": [
            "report_id",
            "sequence"
          ],
          "name": "uq_post_incident_report_action_sequence"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "report_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "incident_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "provider",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "model_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "prompt_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "grounding_hash",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "overall_confidence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "evidence_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "warnings_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "reviewer_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "review_notes",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "reviewed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "approved_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "grounding_hash"
          ],
          "name": "ix_post_incident_reports_grounding_hash",
          "unique": false
        },
        {
          "columns": [
            "incident_id"
          ],
          "name": "ix_post_incident_reports_incident_id",
          "unique": false
        },
        {
          "columns": [
            "provider"
          ],
          "name": "ix_post_incident_reports_provider",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_post_incident_reports_status",
          "unique": false
        }
      ],
      "name": "post_incident_reports",
      "unique_constraints": [
        {
          "columns": [
            "incident_id",
            "version"
          ],
          "name": "uq_post_incident_report_version"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "verification_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "recommendation_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "analysis_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "signal_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "pre_snapshot_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "post_snapshot_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "algorithm_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "generated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "applied_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "confidence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "summary",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "target_entity_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "target_entity_kind",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "target_entity_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "passed_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "failed_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "unknown_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "analysis_id"
          ],
          "name": "ix_recovery_verifications_analysis_id",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_recovery_verifications_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "generated_at"
          ],
          "name": "ix_recovery_verifications_generated_at",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_recovery_verifications_namespace",
          "unique": false
        },
        {
          "columns": [
            "post_snapshot_id"
          ],
          "name": "ix_recovery_verifications_post_snapshot_id",
          "unique": false
        },
        {
          "columns": [
            "pre_snapshot_id"
          ],
          "name": "ix_recovery_verifications_pre_snapshot_id",
          "unique": false
        },
        {
          "columns": [
            "recommendation_id"
          ],
          "name": "ix_recovery_verifications_recommendation_id",
          "unique": false
        },
        {
          "columns": [
            "signal_id"
          ],
          "name": "ix_recovery_verifications_signal_id",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_recovery_verifications_status",
          "unique": false
        },
        {
          "columns": [
            "target_entity_id"
          ],
          "name": "ix_recovery_verifications_target_entity_id",
          "unique": false
        }
      ],
      "name": "recovery_verifications",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "recommendation_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "analysis_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "hypothesis_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "signal_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "change_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "algorithm_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "generated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "action_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "confidence",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "risk",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "target_entity_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "target_entity_kind",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "target_entity_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "applied_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "action_type"
          ],
          "name": "ix_remediation_recommendations_action_type",
          "unique": false
        },
        {
          "columns": [
            "analysis_id"
          ],
          "name": "ix_remediation_recommendations_analysis_id",
          "unique": false
        },
        {
          "columns": [
            "change_id"
          ],
          "name": "ix_remediation_recommendations_change_id",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_remediation_recommendations_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "generated_at"
          ],
          "name": "ix_remediation_recommendations_generated_at",
          "unique": false
        },
        {
          "columns": [
            "hypothesis_id"
          ],
          "name": "ix_remediation_recommendations_hypothesis_id",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_remediation_recommendations_namespace",
          "unique": false
        },
        {
          "columns": [
            "risk"
          ],
          "name": "ix_remediation_recommendations_risk",
          "unique": false
        },
        {
          "columns": [
            "signal_id"
          ],
          "name": "ix_remediation_recommendations_signal_id",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_remediation_recommendations_status",
          "unique": false
        },
        {
          "columns": [
            "target_entity_id"
          ],
          "name": "ix_remediation_recommendations_target_entity_id",
          "unique": false
        }
      ],
      "name": "remediation_recommendations",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "runtime_dependency_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "agent_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "sensor_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "node_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_pod_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_pod_uid",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_workload_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_container_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source_binary",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "source_pid",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "destination_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "destination_address",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "destination_port",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "protocol",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 20
          }
        },
        {
          "name": "direction",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 20
          }
        },
        {
          "name": "observation_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "success_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "failure_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "first_seen_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_seen_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "metadata_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "agent_id"
          ],
          "name": "ix_runtime_dependencies_agent_id",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_runtime_dependencies_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "destination_address"
          ],
          "name": "ix_runtime_dependencies_destination_address",
          "unique": false
        },
        {
          "columns": [
            "destination_name"
          ],
          "name": "ix_runtime_dependencies_destination_name",
          "unique": false
        },
        {
          "columns": [
            "destination_port"
          ],
          "name": "ix_runtime_dependencies_destination_port",
          "unique": false
        },
        {
          "columns": [
            "direction"
          ],
          "name": "ix_runtime_dependencies_direction",
          "unique": false
        },
        {
          "columns": [
            "first_seen_at"
          ],
          "name": "ix_runtime_dependencies_first_seen_at",
          "unique": false
        },
        {
          "columns": [
            "last_seen_at"
          ],
          "name": "ix_runtime_dependencies_last_seen_at",
          "unique": false
        },
        {
          "columns": [
            "node_name"
          ],
          "name": "ix_runtime_dependencies_node_name",
          "unique": false
        },
        {
          "columns": [
            "protocol"
          ],
          "name": "ix_runtime_dependencies_protocol",
          "unique": false
        },
        {
          "columns": [
            "sensor_id"
          ],
          "name": "ix_runtime_dependencies_sensor_id",
          "unique": false
        },
        {
          "columns": [
            "source_binary"
          ],
          "name": "ix_runtime_dependencies_source_binary",
          "unique": false
        },
        {
          "columns": [
            "source_container_id"
          ],
          "name": "ix_runtime_dependencies_source_container_id",
          "unique": false
        },
        {
          "columns": [
            "source_namespace"
          ],
          "name": "ix_runtime_dependencies_source_namespace",
          "unique": false
        },
        {
          "columns": [
            "source_pod_name"
          ],
          "name": "ix_runtime_dependencies_source_pod_name",
          "unique": false
        },
        {
          "columns": [
            "source_pod_uid"
          ],
          "name": "ix_runtime_dependencies_source_pod_uid",
          "unique": false
        },
        {
          "columns": [
            "source_workload_name"
          ],
          "name": "ix_runtime_dependencies_source_workload_name",
          "unique": false
        }
      ],
      "name": "runtime_dependencies",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "runtime_process_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "agent_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "sensor_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "node_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "exec_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "pid",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "binary",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "pod_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "pod_uid",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "container_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "parent_exec_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "exec_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "exit_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "last_exit_code",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "last_signal",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "first_seen_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_seen_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "metadata_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "agent_id"
          ],
          "name": "ix_runtime_processes_agent_id",
          "unique": false
        },
        {
          "columns": [
            "binary"
          ],
          "name": "ix_runtime_processes_binary",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_runtime_processes_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "container_id"
          ],
          "name": "ix_runtime_processes_container_id",
          "unique": false
        },
        {
          "columns": [
            "exec_id"
          ],
          "name": "ix_runtime_processes_exec_id",
          "unique": false
        },
        {
          "columns": [
            "first_seen_at"
          ],
          "name": "ix_runtime_processes_first_seen_at",
          "unique": false
        },
        {
          "columns": [
            "last_seen_at"
          ],
          "name": "ix_runtime_processes_last_seen_at",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_runtime_processes_namespace",
          "unique": false
        },
        {
          "columns": [
            "node_name"
          ],
          "name": "ix_runtime_processes_node_name",
          "unique": false
        },
        {
          "columns": [
            "pod_name"
          ],
          "name": "ix_runtime_processes_pod_name",
          "unique": false
        },
        {
          "columns": [
            "pod_uid"
          ],
          "name": "ix_runtime_processes_pod_uid",
          "unique": false
        },
        {
          "columns": [
            "sensor_id"
          ],
          "name": "ix_runtime_processes_sensor_id",
          "unique": false
        }
      ],
      "name": "runtime_processes",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "sensor_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "agent_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "node_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "source",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "heartbeat_interval_seconds",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "processed_event_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "dropped_event_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "parser_error_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "buffered_batch_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "submitted_batch_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "source_file",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 1000
          }
        },
        {
          "name": "source_file_offset",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "last_error",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "capabilities_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "metadata_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "last_seen_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_heartbeat_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_batch_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "agent_id"
          ],
          "name": "ix_runtime_sensors_agent_id",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_runtime_sensors_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "last_batch_at"
          ],
          "name": "ix_runtime_sensors_last_batch_at",
          "unique": false
        },
        {
          "columns": [
            "last_heartbeat_at"
          ],
          "name": "ix_runtime_sensors_last_heartbeat_at",
          "unique": false
        },
        {
          "columns": [
            "last_seen_at"
          ],
          "name": "ix_runtime_sensors_last_seen_at",
          "unique": false
        },
        {
          "columns": [
            "node_name"
          ],
          "name": "ix_runtime_sensors_node_name",
          "unique": false
        },
        {
          "columns": [
            "source"
          ],
          "name": "ix_runtime_sensors_source",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_runtime_sensors_status",
          "unique": false
        }
      ],
      "name": "runtime_sensors",
      "unique_constraints": [
        {
          "columns": [
            "agent_id",
            "node_name",
            "source"
          ],
          "name": "uq_runtime_sensor_agent_node_source"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "signal_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "fingerprint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "signal_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "severity",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "category",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "source_system",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "title",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "summary",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "reason",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "action",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "first_observed_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_observed_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "occurrence_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "involved_entity_id",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "involved_object_uid",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "involved_object_kind",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "involved_object_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "category"
          ],
          "name": "ix_signals_category",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_signals_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "fingerprint"
          ],
          "name": "ix_signals_fingerprint",
          "unique": false
        },
        {
          "columns": [
            "involved_entity_id"
          ],
          "name": "ix_signals_involved_entity_id",
          "unique": false
        },
        {
          "columns": [
            "involved_object_uid"
          ],
          "name": "ix_signals_involved_object_uid",
          "unique": false
        },
        {
          "columns": [
            "last_observed_at"
          ],
          "name": "ix_signals_last_observed_at",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_signals_namespace",
          "unique": false
        },
        {
          "columns": [
            "reason"
          ],
          "name": "ix_signals_reason",
          "unique": false
        },
        {
          "columns": [
            "severity"
          ],
          "name": "ix_signals_severity",
          "unique": false
        },
        {
          "columns": [
            "signal_type"
          ],
          "name": "ix_signals_signal_type",
          "unique": false
        },
        {
          "columns": [
            "source_system"
          ],
          "name": "ix_signals_source_system",
          "unique": false
        }
      ],
      "name": "signals",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "agent_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "agent_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "cluster_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "environment",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "token_hash",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 64
          }
        },
        {
          "name": "token_hint",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 32
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "collection_interval_seconds",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "heartbeat_interval_seconds",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "namespace_scope_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "capabilities_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "labels_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "metadata_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "buffered_item_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "last_collection_status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_error",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "last_seen_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_heartbeat_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "last_snapshot_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "enrolled_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "revoked_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "agent_type"
          ],
          "name": "ix_topo_agents_agent_type",
          "unique": false
        },
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_topo_agents_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "environment"
          ],
          "name": "ix_topo_agents_environment",
          "unique": false
        },
        {
          "columns": [
            "last_heartbeat_at"
          ],
          "name": "ix_topo_agents_last_heartbeat_at",
          "unique": false
        },
        {
          "columns": [
            "last_seen_at"
          ],
          "name": "ix_topo_agents_last_seen_at",
          "unique": false
        },
        {
          "columns": [
            "last_snapshot_at"
          ],
          "name": "ix_topo_agents_last_snapshot_at",
          "unique": false
        },
        {
          "columns": [
            "name"
          ],
          "name": "ix_topo_agents_name",
          "unique": false
        },
        {
          "columns": [
            "revoked_at"
          ],
          "name": "ix_topo_agents_revoked_at",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_topo_agents_status",
          "unique": false
        },
        {
          "columns": [
            "token_hash"
          ],
          "name": "ix_topo_agents_token_hash",
          "unique": true
        }
      ],
      "name": "topo_agents",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "snapshot_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "schema_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "collected_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "collector_name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "collector_version",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "cluster_name",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "namespace",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "entity_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "relationship_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "evidence_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "scope_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "cluster_name"
          ],
          "name": "ix_topology_snapshots_cluster_name",
          "unique": false
        },
        {
          "columns": [
            "collected_at"
          ],
          "name": "ix_topology_snapshots_collected_at",
          "unique": false
        },
        {
          "columns": [
            "namespace"
          ],
          "name": "ix_topology_snapshots_namespace",
          "unique": false
        }
      ],
      "name": "topology_snapshots",
      "unique_constraints": []
    },
    {
      "columns": [
        {
          "name": "delivery_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "webhook_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "event_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "event_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "resource_type",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 100
          }
        },
        {
          "name": "resource_id",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 500
          }
        },
        {
          "name": "status",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 30
          }
        },
        {
          "name": "attempt_count",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "response_status",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "response_body",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "error_message",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "requested_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "completed_at",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "payload_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "event_id"
          ],
          "name": "ix_webhook_deliveries_event_id",
          "unique": false
        },
        {
          "columns": [
            "event_type"
          ],
          "name": "ix_webhook_deliveries_event_type",
          "unique": false
        },
        {
          "columns": [
            "resource_id"
          ],
          "name": "ix_webhook_deliveries_resource_id",
          "unique": false
        },
        {
          "columns": [
            "resource_type"
          ],
          "name": "ix_webhook_deliveries_resource_type",
          "unique": false
        },
        {
          "columns": [
            "status"
          ],
          "name": "ix_webhook_deliveries_status",
          "unique": false
        },
        {
          "columns": [
            "webhook_id"
          ],
          "name": "ix_webhook_deliveries_webhook_id",
          "unique": false
        }
      ],
      "name": "webhook_deliveries",
      "unique_constraints": [
        {
          "columns": [
            "webhook_id",
            "event_id"
          ],
          "name": "uq_webhook_delivery_event"
        }
      ]
    },
    {
      "columns": [
        {
          "name": "webhook_id",
          "nullable": false,
          "primary_key": true,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "name",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 255
          }
        },
        {
          "name": "url",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 2000
          }
        },
        {
          "name": "event_types_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "headers_json",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "signing_secret",
          "nullable": true,
          "primary_key": false,
          "type": {
            "family": "text"
          }
        },
        {
          "name": "active",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "boolean"
          }
        },
        {
          "name": "timeout_seconds",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "max_attempts",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "integer"
          }
        },
        {
          "name": "created_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        },
        {
          "name": "updated_at",
          "nullable": false,
          "primary_key": false,
          "type": {
            "family": "string",
            "length": 50
          }
        }
      ],
      "indexes": [
        {
          "columns": [
            "active"
          ],
          "name": "ix_webhook_endpoints_active",
          "unique": false
        }
      ],
      "name": "webhook_endpoints",
      "unique_constraints": []
    }
  ]
}
"""
)


def _column_type(spec: dict[str, object]) -> sa.types.TypeEngine:
    family = spec["family"]
    factories: dict[str, Callable[[], sa.types.TypeEngine]] = {
        "boolean": sa.Boolean,
        "float": sa.Float,
        "integer": sa.Integer,
        "text": sa.Text,
    }
    if family == "string":
        return sa.String(length=int(spec["length"]))
    try:
        return factories[str(family)]()
    except KeyError as exc:
        raise RuntimeError(f"Unsupported frozen column type: {family}") from exc


def upgrade() -> None:
    for table in _SCHEMA["tables"]:
        columns = [
            sa.Column(
                column["name"],
                _column_type(column["type"]),
                nullable=column["nullable"],
                primary_key=column["primary_key"],
            )
            for column in table["columns"]
        ]
        constraints = [
            sa.UniqueConstraint(
                *constraint["columns"],
                name=constraint["name"],
            )
            for constraint in table["unique_constraints"]
        ]
        op.create_table(table["name"], *columns, *constraints)

        for index in table["indexes"]:
            op.create_index(
                index["name"],
                table["name"],
                index["columns"],
                unique=index["unique"],
            )


def downgrade() -> None:
    for table in reversed(_SCHEMA["tables"]):
        op.drop_table(table["name"])

