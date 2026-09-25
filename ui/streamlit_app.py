"""Streamlit console. TicketService stays the source of numbers."""

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

CLAUDE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap');

html, body, [class*="st-"], .stApp, .stMarkdown, p, span, label, input, textarea {
  font-family: "Source Sans 3", ui-sans-serif, system-ui, sans-serif !important;
}
h1, h2, h3, .serif {
  font-family: "Source Serif 4", Georgia, serif !important;
  letter-spacing: -0.02em;
  font-weight: 550;
  color: #141413;
}
.stApp { background: #F4F3EE; }
header[data-testid="stHeader"] { background: #F4F3EE; }
#MainMenu, footer, .stDeployButton { visibility: hidden; }
[data-testid="stSidebar"] { background: #FAF9F5; border-right: 1px solid #E8E6DC; }
[data-testid="stSidebar"] * { font-family: "Source Sans 3", sans-serif !important; }

.page-wrap { max-width: 920px; margin: 0 auto 2.5rem; }
.lede { color: #5E5E5A; font-size: 1.02rem; line-height: 1.55; margin: 0.35rem 0 1.4rem; }
.kicker { color: #C96442; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }

.kpi-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 1rem 0 1.4rem; }
@media (min-width: 860px) { .kpi-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.kpi {
  background: #FAF9F5;
  border: 1px solid #E8E6DC;
  border-radius: 14px;
  padding: 16px 16px 14px;
}
.kpi .label { color: #5E5E5A; font-size: 0.82rem; margin-bottom: 6px; }
.kpi .value {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 2rem;
  line-height: 1.1;
  color: #141413;
}
.kpi .hint { color: #6F6E69; font-size: 0.8rem; margin-top: 8px; line-height: 1.4; }

.panel {
  background: #FAF9F5;
  border: 1px solid #E8E6DC;
  border-radius: 14px;
  padding: 18px 18px 14px;
  margin-bottom: 12px;
}
.panel h3 { margin: 0 0 12px; font-size: 1.15rem; }
.mix { display: flex; align-items: center; gap: 10px; margin: 8px 0; font-size: 0.92rem; }
.mix span.name { width: 92px; color: #3D3D3A; }
.mix .track { flex: 1; height: 7px; background: #EDEBE3; border-radius: 99px; overflow: hidden; }
.mix .fill { height: 100%; background: #C96442; border-radius: 99px; }
.mix span.n { width: 36px; text-align: right; color: #141413; font-weight: 600; }

.brief { color: #3D3D3A; line-height: 1.6; font-size: 1.02rem; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 0.4rem 0 1rem; }
</style>
"""


@st.cache_resource
def get_service() -> TicketService:
    service = TicketService(get_settings())
    service.startup()
    return service


def _inject_theme() -> None:
    st.markdown(CLAUDE_CSS, unsafe_allow_html=True)


def _mix_rows(data: dict[str, int]) -> str:
    peak = max(data.values()) if data else 1
    bits = []
    for name, count in sorted(data.items(), key=lambda item: item[1], reverse=True):
        width = max(4, round(100 * count / peak))
        bits.append(
            f'<div class="mix"><span class="name">{name}</span>'
            f'<div class="track"><div class="fill" style="width:{width}%"></div></div>'
            f'<span class="n">{count}</span></div>'
        )
    return "".join(bits)


def _page_overview(service: TicketService) -> None:
    stats = service.stats()
    open_n = stats.by_status.get("Open", 0)
    resolved = stats.by_status.get("Resolved", 0)
    escalated = stats.by_status.get("Escalated", 0)
    total = stats.row_count or 1
    sla = stats.anomaly_counts.sla_breach
    outliers = stats.anomaly_counts.resolution_outlier
    top_cat = max(stats.by_category, key=stats.by_category.get) if stats.by_category else "—"
    busiest = max(stats.by_agent, key=stats.by_agent.get) if stats.by_agent else "—"
    mean_h = stats.resolution_time_hrs.mean
    median_h = stats.resolution_time_hrs.median
    rating = stats.customer_rating.mean

    st.markdown('<p class="kicker">Operations desk</p>', unsafe_allow_html=True)
    st.markdown("## How the queue looks")
    st.markdown(
        f'<p class="lede">As of {stats.reference_now}, {open_n} of {total} tickets are still open '
        f"({round(100 * open_n / total, 1)}%). {sla} High or Critical tickets have already aged past 24 hours. "
        f"{top_cat} is the busiest category; {busiest} holds the largest personal queue.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Still open</div>
            <div class="value">{open_n}</div>
            <div class="hint">{escalated} more are escalated. Resolved volume is {resolved}.</div></div>
          <div class="kpi"><div class="label">SLA at risk</div>
            <div class="value">{sla}</div>
            <div class="hint">Unresolved High/Critical older than 24h vs the dataset clock.</div></div>
          <div class="kpi"><div class="label">Slow resolutions</div>
            <div class="value">{outliers}</div>
            <div class="hint">IQR outliers on resolved time. Median {median_h}h, mean {mean_h}h — the tail is long.</div></div>
          <div class="kpi"><div class="label">Customer rating</div>
            <div class="value">{rating if rating is not None else "—"}</div>
            <div class="hint">Average on rated (resolved) tickets only. Null ratings are left null.</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown(
            f'<div class="panel"><h3>Where work sits</h3>{_mix_rows(stats.by_status)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="panel"><h3>By category</h3>{_mix_rows(stats.by_category)}</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f'<div class="panel"><h3>Urgency mix</h3>{_mix_rows(stats.by_priority)}</div>',
            unsafe_allow_html=True,
        )
        top_agents = dict(sorted(stats.by_agent.items(), key=lambda item: item[1], reverse=True)[:5])
        st.markdown(
            f'<div class="panel"><h3>Busiest agents</h3>{_mix_rows(top_agents)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div class="panel"><h3>What this means</h3>'
        f'<p class="brief">Resolution time is right-skewed: the typical ticket closes in '
        f"{median_h} hours, but the mean is {mean_h} hours because a small set of cases run past "
        f"{stats.resolution_time_hrs.max} hours. Those {outliers} IQR flags and {sla} SLA breaches "
        f"are the first place a lead should look. None of these numbers come from the language model.</p></div>",
        unsafe_allow_html=True,
    )


def _run_question(service: TicketService, question: str) -> None:
    try:
        result = service.query(question)
    except GroqNotConfiguredError as exc:
        st.session_state.chat.append({"role": "assistant", "kind": "error", "text": str(exc)})
        return
    except GroqRequestError as exc:
        st.session_state.chat.append({"role": "assistant", "kind": "error", "text": str(exc)})
        return
    except (QueryTranslationError, SQLGuardError) as exc:
        st.session_state.chat.append({"role": "assistant", "kind": "error", "text": str(exc)})
        return
    st.session_state.chat.append(
        {
            "role": "assistant",
            "kind": "answer",
            "text": result.answer,
            "sql": result.sql,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows": result.rows,
        }
    )


def _page_ask(service: TicketService) -> None:
    if "chat" not in st.session_state:
        st.session_state.chat = []

    st.markdown('<p class="kicker">Ask</p>', unsafe_allow_html=True)
    st.markdown("## Ask about the desk")
    st.markdown(
        '<p class="lede">Ask in plain language. The model writes SQL; SQLite does the arithmetic. '
        "You get a written answer with the real counts inside it.</p>",
        unsafe_allow_html=True,
    )

    for i, sample in enumerate(SAMPLES):
        if st.button(sample, key=f"chip_{i}"):
            st.session_state.pending = sample
            st.rerun()

    for turn in st.session_state.chat:
        with st.chat_message(turn["role"]):
            if turn.get("kind") == "error":
                st.error(turn["text"])
                continue
            st.markdown(turn["text"])
            if turn.get("sql"):
                with st.expander("How this was computed"):
                    st.caption(
                        f"{turn.get('row_count', 0)} matching row(s)"
                        + (" · result capped" if turn.get("truncated") else "")
                    )
                    st.code(turn["sql"], language="sql")

    pending = st.session_state.pop("pending", None)
    typed = st.chat_input("Ask a question about the tickets…")
    question = (typed or pending or "").strip()
    if question:
        st.session_state.chat.append({"role": "user", "kind": "q", "text": question})
        with st.spinner("Looking that up…"):
            _run_question(service, question)
        st.rerun()


def _page_anomalies(service: TicketService) -> None:
    st.markdown('<p class="kicker">Flags</p>', unsafe_allow_html=True)
    st.markdown("## Anomalies")
    st.markdown(
        '<p class="lede">IQR and SLA rules only. The model does not decide what is anomalous.</p>',
        unsafe_allow_html=True,
    )
    left, right = st.columns(2)
    method = left.selectbox("Method", ["iqr", "zscore"])
    anomaly_type = right.selectbox("Type", ["all", "resolution_outlier", "sla_breach"])
    payload = service.anomalies(method=method, anomaly_type=anomaly_type)
    st.caption(f"{payload.count} flags on this filter.")
    rows = [item.model_dump() for item in payload.anomalies]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No anomalies for this filter.")


def _page_tickets(service: TicketService) -> None:
    st.markdown('<p class="kicker">Queue</p>', unsafe_allow_html=True)
    st.markdown("## Tickets")
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
    st.dataframe([item.model_dump() for item in payload.tickets], use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Support Ticket Intelligence", layout="wide")
    _inject_theme()
    service = get_service()
    with st.sidebar:
        st.markdown("### Desk")
        page = st.radio(
            "Go to",
            ["Overview", "Ask the data", "Anomalies", "Ticket queue"],
            label_visibility="collapsed",
        )
    if page == "Overview":
        _page_overview(service)
    elif page == "Ask the data":
        _page_ask(service)
    elif page == "Anomalies":
        _page_anomalies(service)
    else:
        _page_tickets(service)


main()
