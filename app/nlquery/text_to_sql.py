from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.ingestion.schema import SchemaInfo
from app.llm.groq_client import GroqClient
from app.nlquery.prompts import sql_repair_prompt, sql_system_prompt, sql_user_prompt
from app.nlquery.sql_guard import SQLGuardError, validate_sql

logger = logging.getLogger(__name__)


class QueryTranslationError(ValueError):
    """The model did not produce executable SQL."""


@dataclass
class SQLPlan:
    sql: str
    explanation: str


def generate_sql(question: str, schema: SchemaInfo, client: GroqClient) -> SQLPlan:
    system = sql_system_prompt(schema)
    plan = _request_plan(client, system, sql_user_prompt(question))
    try:
        sql = validate_sql(plan.sql)
        return SQLPlan(sql=sql, explanation=plan.explanation)
    except SQLGuardError as exc:
        logger.warning("SQL guard rejected first attempt: %s", exc)
        repaired = _request_plan(
            client,
            system,
            sql_repair_prompt(question, plan.sql, str(exc)),
        )
        try:
            sql = validate_sql(repaired.sql)
        except SQLGuardError as retry_exc:
            raise QueryTranslationError(str(retry_exc)) from retry_exc
        return SQLPlan(sql=sql, explanation=repaired.explanation or plan.explanation)


def _request_plan(client: GroqClient, system: str, user: str) -> SQLPlan:
    raw = client.complete_json(system, user)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QueryTranslationError("Model did not return valid JSON.") from exc
    sql = str(payload.get("sql") or "").strip()
    explanation = str(payload.get("explanation") or "").strip()
    if not sql:
        raise QueryTranslationError("Model returned JSON without an sql field.")
    return SQLPlan(sql=sql, explanation=explanation)
