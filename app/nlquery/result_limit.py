"""Bound generated SELECT results in SQLite so Python never materializes an unbounded set."""


def bound_select(sql: str, limit: int) -> str:
    """Wrap a single SELECT/WITH so the engine itself returns at most `limit` rows."""
    if limit < 1:
        raise ValueError("Result limit must be at least 1.")
    body = (sql or "").strip().rstrip(";")
    if not body:
        raise ValueError("SQL is empty.")
    return f"SELECT * FROM (\n{body}\n) AS _result_cap LIMIT {int(limit)}"


def count_select(sql: str) -> str:
    """Count matches of the original SELECT without loading those rows into Python."""
    body = (sql or "").strip().rstrip(";")
    if not body:
        raise ValueError("SQL is empty.")
    return f"SELECT COUNT(*) AS n FROM (\n{body}\n) AS _count_src"
