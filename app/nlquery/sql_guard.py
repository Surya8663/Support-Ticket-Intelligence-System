from __future__ import annotations

import re

import sqlparse
from sqlparse.tokens import Keyword

ALLOWED_TABLES = frozenset({"tickets", "anomalies"})
FORBIDDEN_KEYWORDS = frozenset(
    {
        "drop",
        "delete",
        "update",
        "insert",
        "alter",
        "attach",
        "detach",
        "pragma",
        "replace",
        "create",
        "truncate",
        "grant",
        "vacuum",
        "reindex",
        "analyze",
        "recursive",
    }
)
FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "sqlite_master",
        "sqlite_temp_master",
        "sqlite_schema",
        "sqlite_sequence",
    }
)
_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
_CTE_RE = re.compile(r"(?:WITH|,)\s*([a-zA-Z_][\w]*)\s+AS\s*\(", re.IGNORECASE)
_JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
_UNION_RE = re.compile(r"\bUNION\b", re.IGNORECASE)


class SQLGuardError(ValueError):
    """Generated SQL failed the safety checks."""


def validate_sql(sql: str, max_joins: int = 2) -> str:
    """Return a cleaned SELECT/WITH statement or raise SQLGuardError.

    This is a read-only allow-list for the prototype, not a complete sandbox.
    Execution still uses a read-only SQLite URI plus a VM timeout.
    """
    cleaned = (sql or "").strip()
    if not cleaned:
        raise SQLGuardError("SQL is empty.")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLGuardError("SQL comments are not allowed.")

    body = cleaned.rstrip(";").strip()
    if ";" in body:
        raise SQLGuardError("Multiple SQL statements are not allowed.")
    if re.search(r"\bINTO\b", body, re.IGNORECASE):
        raise SQLGuardError("SELECT INTO is not allowed.")
    if re.search(r"\bRECURSIVE\b", body, re.IGNORECASE):
        raise SQLGuardError("Recursive CTEs are not allowed.")

    join_count = len(_JOIN_RE.findall(body))
    if join_count > max_joins:
        raise SQLGuardError(f"Query uses {join_count} JOINs; the limit is {max_joins}.")
    if len(_UNION_RE.findall(body)) > 1:
        raise SQLGuardError("At most one UNION is allowed.")

    statements = sqlparse.parse(body)
    if len(statements) != 1:
        raise SQLGuardError("Exactly one SQL statement is required.")

    first = next((token for token in statements[0].tokens if not token.is_whitespace), None)
    if first is None:
        raise SQLGuardError("SQL is empty.")
    start = first.value.upper().split()[0]
    if start not in {"SELECT", "WITH"}:
        raise SQLGuardError("Only SELECT queries are allowed.")

    for token in statements[0].flatten():
        value = token.value.lower()
        if token.ttype in (Keyword, Keyword.DML, Keyword.DDL) and value in FORBIDDEN_KEYWORDS:
            raise SQLGuardError(f"Forbidden keyword: {token.value}")
        if value in FORBIDDEN_KEYWORDS and token.ttype is not None:
            raise SQLGuardError(f"Forbidden keyword: {token.value}")
        if value in FORBIDDEN_IDENTIFIERS:
            raise SQLGuardError(f"System catalog access is not allowed: {token.value}")

    cte_names = {name.lower() for name in _CTE_RE.findall(body)}
    tables = {name.lower() for name in _TABLE_RE.findall(body)}
    unknown = tables - ALLOWED_TABLES - cte_names
    if unknown:
        raise SQLGuardError(f"Query references tables that are not allowed: {sorted(unknown)}")
    if not (tables & ALLOWED_TABLES):
        raise SQLGuardError("Query does not reference an allowed table.")
    return body
