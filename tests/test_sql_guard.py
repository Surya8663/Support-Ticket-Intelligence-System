import pytest

from app.nlquery.sql_guard import SQLGuardError, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM tickets WHERE status = 'Open'",
        "SELECT * FROM anomalies WHERE anomaly_type = 'sla_breach'",
        "WITH x AS (SELECT agent_id FROM tickets) SELECT * FROM x JOIN tickets t ON t.agent_id = x.agent_id",
    ],
)
def test_allows_safe_selects(sql):
    assert "FROM" in validate_sql(sql).upper()


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE tickets",
        "DELETE FROM tickets",
        "INSERT INTO tickets (ticket_id) VALUES ('x')",
        "UPDATE tickets SET status = 'Open'",
        "SELECT * FROM tickets; DELETE FROM tickets",
        "SELECT * FROM users",
        "SELECT * FROM tickets -- wipe",
        "PRAGMA table_info(tickets)",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t) SELECT * FROM tickets",
        "SELECT * FROM sqlite_master",
        "SELECT * INTO tickets FROM tickets",
        "SELECT * FROM tickets JOIN anomalies a ON a.ticket_id = tickets.ticket_id "
        "JOIN anomalies b ON b.ticket_id = tickets.ticket_id "
        "JOIN anomalies c ON c.ticket_id = tickets.ticket_id",
        "ALTER TABLE tickets ADD COLUMN x TEXT",
        "ATTACH DATABASE 'evil.db' AS evil",
    ],
)
def test_rejects_unsafe_sql(sql):
    with pytest.raises(SQLGuardError):
        validate_sql(sql)
