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


def _is_agent_rating_rank(question: str) -> bool:
    text = question.lower()
    if "agent" not in text or "rating" not in text:
        return False
    return any(word in text for word in ("lowest", "highest", "best", "worst", "average", "avg"))


def _sql_averages_rating_by_agent(sql: str) -> bool:
    text = " ".join(sql.lower().split())
    return "avg(" in text and "customer_rating" in text and "group by" in text and "agent_id" in text


class AgentRatingSQLError(SQLGuardError):
    """Generated SQL ranked a single ticket instead of an agent average."""


def generate_sql(
    question: str,
    schema: SchemaInfo,
    client: GroqClient,
    max_joins: int = 2,
) -> SQLPlan:
    system = sql_system_prompt(schema)
    plan = _request_plan(client, system, sql_user_prompt(question))
    try:
        sql = _checked_sql(question, plan.sql, max_joins)
        return SQLPlan(sql=sql, explanation=plan.explanation)
    except SQLGuardError as exc:
        logger.warning("SQL guard rejected first attempt: %s", exc)
        repaired = _request_plan(
            client,
            system,
            sql_repair_prompt(question, plan.sql, str(exc)),
        )
        try:
            sql = _checked_sql(question, repaired.sql, max_joins)
        except SQLGuardError as retry_exc:
            raise QueryTranslationError(str(retry_exc)) from retry_exc
        return SQLPlan(sql=sql, explanation=repaired.explanation or plan.explanation)


def _checked_sql(question: str, sql: str, max_joins: int) -> str:
    validated = validate_sql(sql, max_joins=max_joins)
    if _is_agent_rating_rank(question) and not _sql_averages_rating_by_agent(validated):
        raise AgentRatingSQLError(
            "Agent rating questions must use AVG(customer_rating) GROUP BY agent_id. "
            "Do not rank a single ticket by MIN/MAX(customer_rating)."
        )
    return validated


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
