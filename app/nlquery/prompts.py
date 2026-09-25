from __future__ import annotations

from datetime import datetime, timedelta

from app.ingestion.schema import SchemaInfo

ANOMALIES_SCHEMA = """
Table: anomalies (one row per flagged ticket; a ticket appears at most once per anomaly_type)
Columns:
  - ticket_id TEXT
  - anomaly_type TEXT  -- 'resolution_outlier' or 'sla_breach'
  - metric_name TEXT   -- 'resolution_time_hrs' or 'hours_open'
  - metric_value REAL
  - threshold REAL
  - reason TEXT
  - created_at TEXT
  - category TEXT
  - priority TEXT
  - status TEXT
"""


def date_windows(reference_now: str | None) -> dict[str, str]:
    if not reference_now:
        return {
            "reference_now": "",
            "this_month": "",
            "last_month": "",
            "week_start": "",
            "last_week_start": "",
        }
    now = datetime.strptime(reference_now, "%Y-%m-%d %H:%M:%S")
    if now.month == 1:
        last_month = f"{now.year - 1}-12"
    else:
        last_month = f"{now.year}-{now.month - 1:02d}"
    return {
        "reference_now": reference_now,
        "this_month": now.strftime("%Y-%m"),
        "last_month": last_month,
        "week_start": (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
        "last_week_start": (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"),
    }


def sql_system_prompt(schema: SchemaInfo) -> str:
    windows = date_windows(schema.reference_now)
    return f"""You are a SQLite text-to-SQL translator for a support-ticket database.
You do not answer the question yourself. You only produce a JSON object:
{{"sql": "<single SELECT or WITH statement>", "explanation": "<one sentence>"}}

{schema.prompt_block()}
{ANOMALIES_SCHEMA}

Rules:
- SQLite dialect only. One statement. No comments, no PRAGMA, no DDL/DML.
- Allowed tables: tickets, anomalies.
- Unresolved / not resolved means status IN ('Open', 'Escalated').
- "Open" or "currently open" means status = 'Open' only. Do not include Escalated unless the user says unresolved, open or escalated, or not resolved.
- resolution_time_hrs and customer_rating are NULL for unresolved tickets. Never treat NULL as 0.
- Do not use wall-clock dates. The dataset is historical.
- Relative time MUST use these precomputed windows:
  - reference_now = '{windows['reference_now']}'
  - "this month" / "currently" relative to the dataset: strftime('%Y-%m', created_at) = '{windows['this_month']}'
  - "last month": strftime('%Y-%m', created_at) = '{windows['last_month']}'
  - "this week": created_at >= '{windows['week_start']}' AND created_at <= '{windows['reference_now']}'
  - "last week": created_at >= '{windows['last_week_start']}' AND created_at < '{windows['week_start']}'
- Age in hours: (julianday('{windows['reference_now']}') - julianday(created_at)) * 24.0
- "Not resolved within N hours" means:
    (status = 'Resolved' AND resolution_time_hrs > N)
    OR (status IN ('Open', 'Escalated') AND age_hours > N)
- Questions about anomalies / outliers / SLA breaches should query the anomalies table.
- Alias aggregated columns with clear names.
- Return only JSON. No markdown.

Example of the output shape (syntax only, not an answer):
{{"sql": "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status", "explanation": "Counts tickets by status."}}
"""


def sql_user_prompt(question: str) -> str:
    return f"Question: {question}"


def sql_repair_prompt(question: str, broken_sql: str, error: str) -> str:
    return (
        f"Question: {question}\n"
        f"Your previous SQL was rejected:\n{broken_sql}\n"
        f"Validator error: {error}\n"
        "Return a corrected JSON object with a safe SELECT."
    )


def summary_system_prompt() -> str:
    return """You are a support-desk analyst. Turn SQL result rows into a short spoken answer.
Rules:
- Use only the provided rows and row_count. Never invent tickets, agents, or numbers.
- If row_count is 0, say that no matching tickets were found. Do not guess.
- Write 1–3 complete sentences a manager can read. Put the key number in the sentence, not as a lone digit.
- If many rows were returned, summarize the pattern. List at most five ticket ids.
- Do not mention SQL, row_count, JSON, or that you are a model.
- Return JSON: {"answer": "..."}.
"""


def summary_user_prompt(question: str, sql: str, row_count: int, rows_json: str) -> str:
    return (
        f"Question: {question}\n"
        f"SQL: {sql}\n"
        f"row_count: {row_count}\n"
        f"rows (capped): {rows_json}\n"
    )
