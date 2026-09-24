from __future__ import annotations

import json
import logging

from app.llm.groq_client import GroqClient, GroqRequestError
from app.nlquery.prompts import summary_system_prompt, summary_user_prompt

logger = logging.getLogger(__name__)


def summarize_rows(
    question: str,
    sql: str,
    row_count: int,
    rows: list[dict],
    client: GroqClient,
) -> str:
    if row_count == 0:
        fallback = "No matching tickets were found for that question."
    else:
        fallback = f"The query returned {row_count} row(s)."

    rows_json = json.dumps(rows, default=str)
    try:
        raw = client.complete_json(
            summary_system_prompt(),
            summary_user_prompt(question, sql, row_count, rows_json),
        )
        payload = json.loads(raw)
        answer = str(payload.get("answer") or "").strip()
        if answer:
            return answer
    except (GroqRequestError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Summarizer fell back to template: %s", exc)
    return fallback
