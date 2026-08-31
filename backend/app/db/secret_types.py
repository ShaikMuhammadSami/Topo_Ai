"""Protect ordinary bound-parameter representations, not arbitrary DB dumps."""

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


class ProtectedBytes(bytes):
    def __repr__(self):
        return "<protected-bytes>"

    __str__ = __repr__


class SecretBinary(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return ProtectedBytes(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return ProtectedBytes(value) if value is not None else None
