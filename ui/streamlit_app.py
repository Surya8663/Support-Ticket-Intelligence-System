"""Python UI for the assessment. Thin Streamlit shell over TicketService — no second algorithm."""

from __future__ import annotations

import streamlit as st

from app.config import get_settings
from app.llm.groq_client import GroqNotConfiguredError, GroqRequestError
from app.nlquery.sql_guard import SQLGuardError
from app.nlquery.text_to_sql import QueryTranslationError
from app.services.ticket_service import TicketService

SAMPLES = [
    "How many tickets are currently open?",
    "Which agent resolved the most tickets this month?",
    "Show me all Critical tickets not resolved within 12 hours.",
    "What is the average customer rating for Technical category tickets?",
    "Are there any anomalies in resolution times this week?",
]


@st.cache_resource
def get_service() -> TicketService:
    service = TicketService(get_settings())
    service.startup()
    return service


def _page_overview(service: TicketService) -> None:
    health = service.health()
    stats = service.stats()
    st.subheader("Desk snapshot")
    st.caption(
        f"Deterministic SQLite counts. Dataset clock is `{health.reference_now}`. "
        f"Groq configured: {health.groq_configured}."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickets", stats.row_count)
    c2.metric("Open", stats.by_status.get("Open", 0))
    c3.metric("SLA breaches", stats.anomaly_counts.sla_breach)
    c4.metric("IQR outliers", stats.anomaly_counts.resolution_outlier)

    left, right = st.columns(2)
    with left:
        st.markdown("**By status**")
        st.bar_chart(stats.by_status)
        st.markdown("**By category**")
        st.bar_chart(stats.by_category)
    with right:
        st.markdown("**By priority**")
        st.bar_chart(stats.by_priority)
        st.markdown("**Resolved-ticket quality**")
        st.write(
            f"Average rating **{stats.customer_rating.mean}** · "
            f"median resolution **{stats.resolution_time_hrs.median}h** · "
            f"longest **{stats.resolution_time_hrs.max}h**"
        )


def _page_ask(service: TicketService) -> None:
    st.subheader("Ask the data")
    st.caption("Groq writes SQL. SQLite computes. Generated SQL is always shown.")
    sample = st.selectbox("Sample questions", SAMPLES)
    question = st.text_area("Question", value=sample, height=90)
    if st.button("Run query", type="primary", disabled=len(question.strip()) < 3):
        try:
            result = service.query(question.strip())
        except GroqNotConfiguredError as exc:
            st.error(str(exc))
            return
        except GroqRequestError as exc:
            st.error(str(exc))
            return
        except (QueryTranslationError, SQLGuardError) as exc:
            st.error(str(exc))
            return
        st.success(result.answer)
        st.caption(result.explanation)
        st.caption(f"{result.row_count} matching row(s). Truncated: {result.truncated}")
        st.code(result.sql, language="sql")
        if result.rows:
            st.dataframe(result.rows, use_container_width=True, hide_index=True)


def _page_anomalies(service: TicketService) -> None:
    st.subheader("Anomalies")
    method = st.selectbox("Method", ["iqr", "zscore"])
    anomaly_type = st.selectbox("Type", ["all", "resolution_outlier", "sla_breach"])
    payload = service.anomalies(method=method, anomaly_type=anomaly_type)
    st.caption(f"{payload.count} flags. Detection is statistical, not an LLM judgment.")
    rows = [item.model_dump() for item in payload.anomalies]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No anomalies for this filter.")


def _page_tickets(service: TicketService) -> None:
    st.subheader("Ticket queue")
    c1, c2, c3, c4 = st.columns(4)
    status = c1.selectbox("Status", ["", "Open", "Resolved", "Escalated"])
    priority = c2.selectbox("Priority", ["", "Low", "Medium", "High", "Critical"])
    category = c3.selectbox("Category", ["", "Billing", "Technical", "General"])
    search = c4.text_input("Search")
    payload = service.list_tickets(
        status=status or None,
        priority=priority or None,
        category=category or None,
        search=search or None,
        limit=50,
        offset=0,
    )
    st.caption(f"Showing {payload.count} of {payload.total}")
    st.dataframe(
        [item.model_dump() for item in payload.tickets],
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(page_title="Support Ticket Intelligence", layout="wide")
    st.title("Support Ticket Intelligence")
    st.caption("Python UI · FastAPI owns the same TicketService · React is an optional extra console")
    service = get_service()
    page = st.sidebar.radio("Go to", ["Overview", "Ask the data", "Anomalies", "Ticket queue"])
    if page == "Overview":
        _page_overview(service)
    elif page == "Ask the data":
        _page_ask(service)
    elif page == "Anomalies":
        _page_anomalies(service)
    else:
        _page_tickets(service)


main()
