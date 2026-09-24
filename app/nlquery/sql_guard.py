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
    }
)
_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
_CTE_RE = re.compile(r"(?:WITH|,)\s*([a-zA-Z_][\w]*)\s+AS\s*\(", re.IGNORECASE)


class SQLGuardError(ValueError):
    """Generated SQL failed the safety checks."""


def validate_sql(sql: str) -> str:
    """Return a cleaned SELECT/WITH statement or raise SQLGuardError."""
    cleaned = (sql or "").strip()
    if not cleaned:
        raise SQLGuardError("SQL is empty.")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLGuardError("SQL comments are not allowed.")

    body = cleaned.rstrip(";").strip()
    if ";" in body:
        raise SQLGuardError("Multiple SQL statements are not allowed.")

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
        if token.ttype in (Keyword, Keyword.DML, Keyword.DDL) and token.value.lower() in FORBIDDEN_KEYWORDS:
            raise SQLGuardError(f"Forbidden keyword: {token.value}")
        if token.value.lower() in FORBIDDEN_KEYWORDS and token.ttype is not None:
            raise SQLGuardError(f"Forbidden keyword: {token.value}")

    cte_names = {name.lower() for name in _CTE_RE.findall(body)}
    tables = {name.lower() for name in _TABLE_RE.findall(body)}
    unknown = tables - ALLOWED_TABLES - cte_names
    if unknown:
        raise SQLGuardError(f"Query references tables that are not allowed: {sorted(unknown)}")
    if not (tables & ALLOWED_TABLES):
        raise SQLGuardError("Query does not reference an allowed table.")
    return body
