"""Explicit, non-serialized ownership for request-local world-model values.

Persistence is the authority. A reused derived value must carry the ownership
established by its repository/service boundary, not just a matching public ID.
No current-tenant global, identity rewriting, cache, graph algorithm, or scoring
rule lives here. Source input is bound only at an authenticated ingestion boundary.
"""

from dataclasses import dataclass
from functools import wraps
from inspect import signature
from typing import TypeVar

from pydantic import BaseModel

from app.repositories.tenant_scope import (
    TenantResourceNotFound, tenant_value,
)

Value = TypeVar("Value")
_ATTRIBUTE = "_topo_world_ownership"


@dataclass(frozen=True)
class _Ownership:
    tenant_id: str


def _values(value, visited):
    if id(value) in visited:
        return
    visited.add(id(value))
    if isinstance(value, BaseModel):
        yield value
        for name in type(value).model_fields:
            yield from _values(getattr(value, name), visited)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _values(item, visited)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _values(item, visited)


def bind_world_value(value: Value, *, tenant_id: str) -> Value:
    """Attest an owned result; reject mixed ownership before marking anything.

The attribute is not a Pydantic field, JSON key, public ID, or accepted authority
claim. Deep model copies retain it; JSON round trips require repository authority
again. Checking child models also rejects a foreign node appended to an A graph.
"""
    owner = tenant_value(tenant_id)
    models = tuple(_values(value, set()))
    for model in models:
        existing = getattr(model, _ATTRIBUTE, None)
        if existing is not None and (
            not isinstance(existing, _Ownership) or existing.tenant_id != owner
        ):
            raise TenantResourceNotFound()
    for model in models:
        object.__setattr__(model, _ATTRIBUTE, _Ownership(owner))
    return value


def require_world_value(value, *, tenant_id: str) -> None:
    owner = tenant_value(tenant_id)
    marker = getattr(value, _ATTRIBUTE, None)
    if not isinstance(marker, _Ownership) or marker.tenant_id != owner:
        raise TenantResourceNotFound()
    # Every child must have crossed the same producer boundary. A deserialized
    # or otherwise unowned child inserted later is not authoritative either.
    for model in _values(value, set()):
        marker = getattr(model, _ATTRIBUTE, None)
        if not isinstance(marker, _Ownership) or marker.tenant_id != owner:
            raise TenantResourceNotFound()


def tenant_world(*, prefetched=()):
    """Explicit boundary on named services, not a process/session tenant hook.

Validates reused inputs before any service work (including optional LLM calls),
then marks the result for same-tenant reuse without repeated database scans.
"""
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        def scoped(*args, **kwargs):
            supplied = parameters.bind(*args, **kwargs).arguments
            owner = tenant_value(supplied["tenant_id"])
            for name in prefetched:
                value = supplied.get(name)
                if value is not None:
                    require_world_value(value, tenant_id=owner)
            return bind_world_value(function(*args, **kwargs), tenant_id=owner)

        return scoped
    return decorate


def snapshot_from_owned_record(record, *, tenant_id: str):
    """Construct one graph only from a same-tenant persisted snapshot row."""
    from app.db.models import SnapshotRecord
    from app.models.topology import GraphSnapshot

    owner = tenant_value(tenant_id)
    if not isinstance(record, SnapshotRecord) or record.tenant_id != owner:
        raise TenantResourceNotFound()
    snapshot = GraphSnapshot.model_validate_json(record.payload_json)
    if snapshot.snapshot_id != record.snapshot_id:
        raise TenantResourceNotFound()
    return bind_world_value(snapshot, tenant_id=owner)
