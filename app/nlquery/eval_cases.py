from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    question: str
    intent: str
    sql: str
    expected_count: int | None = None
    expected_scalar: float | int | str | None = None
    scalar_column: str | None = None
    scalar_round: int | None = None


GOLDEN_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        question="How many tickets are currently open?",
        intent="COUNT where status='Open' only",
        sql="SELECT COUNT(*) AS value FROM tickets WHERE status = 'Open'",
        expected_scalar=111,
        scalar_column="value",
    ),
    EvalCase(
        question="Which agent resolved the most tickets this month?",
        intent="Top resolved agent in 2024-03",
        sql="""
            SELECT agent_id AS value, COUNT(*) AS resolved_count
            FROM tickets
            WHERE status = 'Resolved' AND strftime('%Y-%m', created_at) = '2024-03'
            GROUP BY agent_id
            ORDER BY resolved_count DESC
            LIMIT 1
        """,
        expected_scalar="AGT-01",
        scalar_column="value",
        expected_count=1,
    ),
    EvalCase(
        question="Show me all Critical tickets not resolved within 12 hours.",
        intent="Critical resolved>12h or unresolved age>12h",
        sql="""
            SELECT ticket_id
            FROM tickets
            WHERE priority = 'Critical'
              AND (
                    (status = 'Resolved' AND resolution_time_hrs > 12)
                 OR (status IN ('Open', 'Escalated')
                     AND (julianday('2024-03-30 18:06:00') - julianday(created_at)) * 24.0 > 12)
              )
        """,
        expected_count=34,
    ),
    EvalCase(
        question="What is the average customer rating for Technical category tickets?",
        intent="AVG(customer_rating) for Technical; NULLs excluded",
        sql="SELECT AVG(customer_rating) AS value FROM tickets WHERE category = 'Technical'",
        expected_scalar=3.74,
        scalar_column="value",
        scalar_round=2,
    ),
    EvalCase(
        question="Are there any anomalies in resolution times this week?",
        intent="IQR outliers created in the dataset week",
        sql="""
            SELECT ticket_id
            FROM anomalies
            WHERE anomaly_type = 'resolution_outlier'
              AND created_at >= '2024-03-23 18:06:00'
              AND created_at <= '2024-03-30 18:06:00'
        """,
        expected_count=6,
    ),
    EvalCase(
        question="How many unresolved critical tickets are there?",
        intent="priority=Critical and status in Open/Escalated",
        sql="""
            SELECT COUNT(*) AS value FROM tickets
            WHERE priority = 'Critical' AND status IN ('Open', 'Escalated')
        """,
        expected_scalar=31,
        scalar_column="value",
    ),
    EvalCase(
        question="Show high-priority tickets older than 24 hours.",
        intent="Unresolved High/Critical with age > 24h vs reference_now",
        sql="""
            SELECT ticket_id FROM tickets
            WHERE priority IN ('High', 'Critical')
              AND status IN ('Open', 'Escalated')
              AND (julianday('2024-03-30 18:06:00') - julianday(created_at)) * 24.0 > 24
        """,
        expected_count=80,
    ),
    EvalCase(
        question="Which agent has the lowest customer rating?",
        intent="MIN AVG(customer_rating) among rated tickets",
        sql="""
            SELECT agent_id AS value, AVG(customer_rating) AS avg_rating
            FROM tickets
            WHERE customer_rating IS NOT NULL
            GROUP BY agent_id
            ORDER BY avg_rating ASC
            LIMIT 1
        """,
        expected_scalar="AGT-08",
        scalar_column="value",
        expected_count=1,
    ),
    EvalCase(
        question="Show unresolved Technical tickets.",
        intent="category=Technical and unresolved",
        sql="""
            SELECT ticket_id FROM tickets
            WHERE category = 'Technical' AND status IN ('Open', 'Escalated')
        """,
        expected_count=48,
    ),
    EvalCase(
        question="What percentage of tickets are escalated?",
        intent="Escalated / 500 * 100",
        sql="""
            SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Escalated' THEN 1 ELSE 0 END) / COUNT(*), 2) AS value
            FROM tickets
        """,
        expected_scalar=12.4,
        scalar_column="value",
        scalar_round=2,
    ),
    EvalCase(
        question="What is the average resolution time for Critical tickets?",
        intent="AVG resolution_time_hrs for resolved Critical",
        sql="""
            SELECT AVG(resolution_time_hrs) AS value
            FROM tickets
            WHERE priority = 'Critical' AND resolution_time_hrs IS NOT NULL
        """,
        expected_scalar=10.629,
        scalar_column="value",
        scalar_round=3,
    ),
    EvalCase(
        question="How many Billing tickets were resolved in the dataset's latest month?",
        intent="Resolved Billing in 2024-03",
        sql="""
            SELECT COUNT(*) AS value FROM tickets
            WHERE category = 'Billing' AND status = 'Resolved'
              AND strftime('%Y-%m', created_at) = '2024-03'
        """,
        expected_scalar=34,
        scalar_column="value",
    ),
)
