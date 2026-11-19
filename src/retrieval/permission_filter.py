from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
import uuid

from src.permissions.service import AccessScope, PermissionDenied


def _payload(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        payload = record.get("payload", record)
        if isinstance(payload, Mapping):
            nested = payload.get("metadata")
            return nested if isinstance(nested, Mapping) else payload
    payload = getattr(record, "payload", None)
    if isinstance(payload, Mapping):
        nested = payload.get("metadata")
        return nested if isinstance(nested, Mapping) else payload
    return {}


def filter_metadata_documents(
    records: Iterable[Any], scope: AccessScope
) -> list[Any]:
    """Keep only table/column metadata allowed by the computed scope.

    Records without a table_id are rejected. Column records must include both
    table_id and column_id so a table grant cannot accidentally expose columns.
    Call this before building LLM context or returning metadata to the client.
    """
    visible = []
    for record in records:
        payload = _payload(record)
        raw_table_id = payload.get("table_id")
        if raw_table_id is None:
            continue
        try:
            table_id = uuid.UUID(str(raw_table_id))
        except (TypeError, ValueError):
            continue

        raw_column_id = payload.get("column_id")
        if raw_column_id is None:
            if scope.allows_table(table_id):
                visible.append(record)
            continue
        try:
            column_id = uuid.UUID(str(raw_column_id))
        except (TypeError, ValueError):
            continue
        if scope.allows_column(table_id, column_id):
            visible.append(record)
    return visible


def require_resources_allowed(
    scope: AccessScope,
    *,
    table_ids: Iterable[uuid.UUID | str],
    columns_by_table: Mapping[uuid.UUID | str, Iterable[uuid.UUID | str]],
) -> None:
    """Raise PermissionDenied if a generated query references blocked resources."""
    for table_id in table_ids:
        if not scope.allows_table(table_id):
            raise PermissionDenied(f"Access to table {table_id} is denied")
    for table_id, column_ids in columns_by_table.items():
        if not scope.allows_table(table_id):
            raise PermissionDenied(f"Access to table {table_id} is denied")
        for column_id in column_ids:
            if not scope.allows_column(table_id, column_id):
                raise PermissionDenied(f"Access to column {column_id} is denied")
