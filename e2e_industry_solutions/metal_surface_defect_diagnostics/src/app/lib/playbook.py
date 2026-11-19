"""Playbook index lookup: reads `defect_playbook` through the SQL warehouse.

Uses the SDK Statement Execution API with named parameters. Array columns come back as JSON
strings and are decoded to lists.
"""

from __future__ import annotations

import json
import re
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState

ARRAY_FIELDS = (
    "visual_indicators",
    "typical_root_causes",
    "recommended_inspection",
    "recommended_repair",
    "escalation_criteria",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_\-]+$")
_TERMINAL = {StatementState.SUCCEEDED, StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED}


class PlaybookError(RuntimeError):
    """The playbook index could not be read."""


def quote_table(full_name: str, kind: str = "table") -> str:
    """Validate a catalog.schema.name identifier and return it backtick-quoted."""
    parts = full_name.split(".")
    if len(parts) != 3 or not all(_IDENTIFIER.match(p) for p in parts):
        raise ValueError(f"Invalid {kind} name (expected catalog.schema.name): {full_name!r}")
    return ".".join(f"`{p}`" for p in parts)


def _decode_row(columns: list[str], row: list) -> dict:
    entry = dict(zip(columns, row))
    for field in ARRAY_FIELDS:
        value = entry.get(field)
        if isinstance(value, str):
            entry[field] = json.loads(value)
        elif value is None:
            entry[field] = []
    return entry


def run_statement(
    w: WorkspaceClient,
    warehouse_id: str,
    statement: str,
    params: list[StatementParameterListItem],
    timeout_s: int = 180,
):
    """Execute a parameterised statement and wait for it (the warehouse may be cold-starting)."""
    response = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=statement, parameters=params, wait_timeout="30s"
    )
    deadline = time.time() + timeout_s
    while response.status.state not in _TERMINAL:
        if time.time() > deadline:
            w.statement_execution.cancel_execution(response.statement_id)
            raise PlaybookError(f"SQL statement timed out after {timeout_s}s")
        time.sleep(2)
        response = w.statement_execution.get_statement(response.statement_id)
    if response.status.state != StatementState.SUCCEEDED:
        error = response.status.error.message if response.status.error else response.status.state.value
        raise PlaybookError(f"SQL statement failed: {error}")
    return response


def fetch_entries(
    w: WorkspaceClient,
    warehouse_id: str,
    table: str,
    defect_classes: list[str],
    timeout_s: int = 180,
) -> dict[str, dict]:
    """Return {defect_class: playbook entry} for the requested classes (missing classes absent)."""
    if not defect_classes:
        return {}
    names = [f"c{i}" for i in range(len(defect_classes))]
    statement = (
        f"SELECT * EXCEPT (loaded_at), CAST(loaded_at AS STRING) AS loaded_at "
        f"FROM {quote_table(table)} WHERE defect_class IN ({', '.join(':' + n for n in names)})"
    )
    params = [StatementParameterListItem(name=n, value=c) for n, c in zip(names, defect_classes)]
    response = run_statement(w, warehouse_id, statement, params, timeout_s)

    columns = [c.name for c in response.manifest.schema.columns]
    rows = (response.result.data_array if response.result else None) or []
    entries = [_decode_row(columns, row) for row in rows]
    return {e["defect_class"]: e for e in entries}
