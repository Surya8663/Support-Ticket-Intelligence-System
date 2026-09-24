from __future__ import annotations

from dataclasses import dataclass, field

REQUIRED_COLUMNS = (
    "ticket_id",
    "created_at",
    "category",
    "priority",
    "status",
    "response_time_hrs",
    "resolution_time_hrs",
    "agent_id",
    "customer_rating",
    "issue_summary",
)

NULLABLE_COLUMNS = frozenset({"resolution_time_hrs", "customer_rating"})

EXPECTED_CATEGORIES = frozenset({"Billing", "Technical", "General"})
EXPECTED_PRIORITIES = frozenset({"Low", "Medium", "High", "Critical"})
EXPECTED_STATUSES = frozenset({"Open", "Resolved", "Escalated"})

# Human-readable notes injected into the text-to-SQL prompt later.
COLUMN_NOTES = {
    "ticket_id": "Unique ticket identifier (e.g. TKT-001).",
    "created_at": "Ticket creation timestamp (YYYY-MM-DD HH:MM).",
    "category": "One of Billing, Technical, General.",
    "priority": "One of Low, Medium, High, Critical.",
    "status": "One of Open, Resolved, Escalated.",
    "response_time_hrs": "Hours from creation to first agent response. Always present.",
    "resolution_time_hrs": (
        "Hours from creation to resolution. NULL when status is Open or Escalated. "
        "Do not treat NULL as zero."
    ),
    "agent_id": "Assigned support agent identifier (e.g. AGT-01).",
    "customer_rating": (
        "Post-resolution satisfaction score 1-5. NULL when status is Open or Escalated."
    ),
    "issue_summary": "Free-text description of the reported issue.",
}


@dataclass
class ColumnInfo:
    name: str
    sql_type: str
    nullable: bool
    note: str = ""


@dataclass
class SchemaInfo:
    table_name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    row_count: int = 0
    reference_now: str | None = None
    warnings: list[str] = field(default_factory=list)

    def prompt_block(self) -> str:
        """Schema description for the LLM. Built at runtime from the loaded file."""
        lines = [
            f"Table: {self.table_name} ({self.row_count} rows)",
            f"Reference 'now' for relative dates (this week / this month): {self.reference_now}",
            "Columns:",
        ]
        for col in self.columns:
            null_flag = "NULLABLE" if col.nullable else "NOT NULL"
            note = f" — {col.note}" if col.note else ""
            lines.append(f"  - {col.name} {col.sql_type} {null_flag}{note}")
        return "\n".join(lines)


class MissingColumnsError(ValueError):
    """Raised when the CSV is missing required columns."""
