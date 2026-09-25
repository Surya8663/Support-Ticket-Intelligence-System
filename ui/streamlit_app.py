"""Streamlit console. TicketService stays the source of numbers."""

from __future__ import annotations

import html

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

PAGES = ["Overview", "Ask the data", "Anomalies", "Tickets"]

# Claude-light tokens. Do not set font-family on span/* — that turns
# Streamlit Material icon ligatures into raw words like
# "keyboard_double_arrow_left", "face", and "arrow_right".
CLAUDE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap');

:root {
  --bg: #F4F3EE;
  --surface: #FAF9F5;
  --border: #E8E6DC;
  --text: #141413;
  --muted: #5E5E5A;
  --accent: #C96442;
  --danger: #B42318;
  --danger-bg: #FBE9E7;
}

html, body, .stApp, .stMarkdown, p, label, input, textarea, button,
[data-testid="stWidgetLabel"], [data-testid="stMarkdownContainer"] {
  font-family: "Source Sans 3", ui-sans-serif, system-ui, sans-serif;
}
h1, h2, h3, .serif {
  font-family: "Source Serif 4", Georgia, serif;
  letter-spacing: -0.02em;
  font-weight: 550;
  color: var(--text);
}
.stApp { background: var(--bg); }
.stMainBlockContainer, .block-container {
  padding-top: 2.25rem !important;
  padding-bottom: 5rem !important;
  max-width: 880px;
}

/* Hide Streamlit chrome that leaks Material icon names as text */
header[data-testid="stHeader"],
div[data-testid="stToolbar"],
div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"],
[data-testid="stAppDeployButton"],
.stAppDeployButton,
.stDeployButton,
#MainMenu,
footer,
[data-testid="stHeaderActionElements"] {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  overflow: hidden !important;
}

[data-testid="stSidebar"] {
  background: var(--surface);
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .block-container { padding-top: 1.25rem; }

.brand { padding: 4px 8px 18px; }
.brand-name {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.2rem;
  color: var(--text);
  letter-spacing: -0.02em;
}
.brand-sub { color: var(--muted); font-size: 0.82rem; margin-top: 2px; }

[data-testid="stSidebar"] .stRadio [role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] .stRadio label {
  padding: 10px 12px !important;
  border-radius: 10px;
  min-height: 44px;
  cursor: pointer;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #F0EEE6; }
[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] { align-items: center; }

.page-kicker {
  color: var(--accent);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin: 0 0 0.35rem;
}
.lede { color: var(--muted); font-size: 1.02rem; line-height: 1.6; margin: 0.35rem 0 1.4rem; }

.kpi-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 1rem 0 1.4rem; }
@media (min-width: 860px) { .kpi-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.kpi {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 16px 14px;
}
.kpi .label { color: var(--muted); font-size: 0.82rem; margin-bottom: 6px; }
.kpi .value {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 2rem;
  line-height: 1.1;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.kpi .hint { color: #6F6E69; font-size: 0.8rem; margin-top: 8px; line-height: 1.4; }

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 18px 14px;
  margin-bottom: 12px;
}
.panel h3 { margin: 0 0 12px; font-size: 1.15rem; }
.mix { display: flex; align-items: center; gap: 10px; margin: 8px 0; font-size: 0.92rem; }
.mix span.name { width: 92px; color: #3D3D3A; }
.mix .track { flex: 1; height: 7px; background: #EDEBE3; border-radius: 99px; overflow: hidden; }
.mix .fill { height: 100%; background: var(--accent); border-radius: 99px; }
.mix span.n { width: 36px; text-align: right; color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }
.brief { color: #3D3D3A; line-height: 1.6; font-size: 1.02rem; }

.thread { display: flex; flex-direction: column; gap: 1.75rem; margin: 0.5rem 0 1.5rem; }
.msg.user { display: flex; justify-content: flex-end; }
.msg.user .bubble {
  max-width: min(36rem, 78%);
  background: #EDEBE3;
  border-radius: 18px 18px 6px 18px;
  padding: 12px 16px;
  line-height: 1.55;
  color: var(--text);
  font-size: 0.98rem;
}
.msg.assistant { max-width: 40rem; }
.msg.assistant p {
  font-size: 1.05rem;
  line-height: 1.7;
  color: var(--text);
  margin: 0 0 0.7rem;
}
.msg.assistant.error {
  background: var(--danger-bg);
  border: 1px solid #F0C4BE;
  border-radius: 12px;
  padding: 12px 14px;
}
.msg.assistant.error p { color: var(--danger); margin: 0; font-size: 0.95rem; }

.sql-drawer {
  margin-top: 4px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 0 14px;
}
.sql-drawer summary {
  cursor: pointer;
  list-style: none;
  padding: 12px 0;
  color: var(--muted);
  font-size: 0.88rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sql-drawer summary::-webkit-details-marker { display: none; }
.sql-drawer summary:hover { color: var(--text); }
.sql-drawer summary::after {
  content: "";
  width: 7px;
  height: 7px;
  border-right: 1.5px solid #8A8A84;
  border-bottom: 1.5px solid #8A8A84;
  transform: rotate(45deg);
  margin-left: 12px;
  flex: 0 0 auto;
}
details.sql-drawer[open] summary::after { transform: rotate(-135deg); margin-top: 4px; }
.sql-meta { color: var(--muted); font-size: 0.82rem; margin: 0 0 8px; }
.sql-drawer pre {
  margin: 0 0 14px;
  padding: 12px;
  background: #F4F3EE;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--text);
}

.empty-chat {
  border: 1px dashed var(--border);
  border-radius: 16px;
  padding: 28px 22px;
  background: var(--surface);
  margin: 0.4rem 0 1.4rem;
}
.empty-title {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.25rem;
  margin: 0 0 6px;
  color: var(--text);
}
.empty-copy { color: var(--muted); line-height: 1.55; margin: 0; }

.stButton > button {
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.9rem;
  min-height: 44px;
  padding: 0.45rem 0.95rem;
  cursor: pointer;
  transition: background 180ms ease, border-color 180ms ease;
}
.stButton > button:hover { background: #F0EEE6; border-color: #D9D6C8; }
.stButton > button:focus-visible { outline: 3px solid rgba(201, 100, 66, 0.35); outline-offset: 2px; }
.stFormSubmitButton > button {
  background: var(--accent) !important;
  color: #fff !important;
  border: none !important;
  min-height: 44px !important;
  min-width: 96px !important;
  padding: 0 22px !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
  cursor: pointer;
}
.stFormSubmitButton > button:hover { filter: brightness(0.96); }
.stTextArea textarea {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  font-size: 1rem !important;
  line-height: 1.5 !important;
  min-height: 88px !important;
}
.stTextArea textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(201, 100, 66, 0.18) !important;
}

@media (prefers-reduced-motion: reduce) {
  .stButton > button, .stFormSubmitButton > button { transition: none; }
}
</style>
"""


@st.cache_resource
def get_service() -> TicketService:
    service = TicketService(get_settings())
    service.startup()
    return service


def _inject_theme() -> None:
    st.markdown(CLAUDE_CSS, unsafe_allow_html=True)


def _esc(text: object) -> str:
    return html.escape(str(text or ""), quote=True)


def _prose(text: str) -> str:
    parts = [part.strip() for part in _esc(text).split("\n") if part.strip()]
    return "".join(f"<p>{part}</p>" for part in parts) or "<p></p>"


def _mix_rows(data: dict[str, int]) -> str:
    peak = max(data.values()) if data else 1
    bits = []
    for name, count in sorted(data.items(), key=lambda item: item[1], reverse=True):
        width = max(4, round(100 * count / peak))
        bits.append(
            f'<div class="mix"><span class="name">{_esc(name)}</span>'
            f'<div class="track"><div class="fill" style="width:{width}%"></div></div>'
            f'<span class="n">{count}</span></div>'
        )
    return "".join(bits)


def _render_thread(turns: list[dict]) -> str:
    if not turns:
        return (
            '<div class="empty-chat">'
            '<p class="empty-title">Ask anything about the ticket desk</p>'
            '<p class="empty-copy">Open tickets, agent load, ratings, SLA breaches — '
            "written as a short answer, with the real counts inside the sentence.</p>"
            "</div>"
        )

    bits = ['<div class="thread">']
    for turn in turns:
        if turn["role"] == "user":
            bits.append(f'<div class="msg user"><div class="bubble">{_esc(turn["text"])}</div></div>')
            continue
        if turn.get("kind") == "error":
            bits.append(f'<div class="msg assistant error">{_prose(turn["text"])}</div>')
            continue
        extra = ""
        if turn.get("sql"):
            cap = " · showing a capped sample" if turn.get("truncated") else ""
            extra = (
                '<details class="sql-drawer">'
                "<summary>How this was computed</summary>"
                f'<p class="sql-meta">{turn.get("row_count", 0)} matching row(s){cap}</p>'
                f"<pre><code>{_esc(turn['sql'])}</code></pre>"
                "</details>"
            )
        bits.append(f'<div class="msg assistant">{_prose(turn["text"])}{extra}</div>')
    bits.append("</div>")
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

    st.markdown('<p class="page-kicker">Overview</p>', unsafe_allow_html=True)
    st.markdown("## How the queue looks")
    st.markdown(
        f'<p class="lede">As of {stats.reference_now}, {open_n} of {total} tickets are still open '
        f"({round(100 * open_n / total, 1)}%). {sla} High or Critical tickets have already aged past 24 hours. "
        f"{_esc(top_cat)} is the busiest category; {_esc(busiest)} holds the largest personal queue.</p>",
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

    st.markdown('<p class="page-kicker">Ask the data</p>', unsafe_allow_html=True)
    st.markdown("## What do you want to know?")
    st.markdown(
        '<p class="lede">Ask in plain English. Groq writes the SQL. SQLite does the arithmetic. '
        "The reply is a written answer with the real counts inside the sentence.</p>",
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for i, sample in enumerate(SAMPLES):
        if cols[i % 2].button(sample, key=f"chip_{i}", use_container_width=True):
            st.session_state.pending = sample
            st.rerun()

    st.markdown(_render_thread(st.session_state.chat), unsafe_allow_html=True)

    pending = st.session_state.pop("pending", None)
    with st.form("ask_form", clear_on_submit=True):
        typed = st.text_area(
            "Question",
            placeholder="Ask a question about the tickets…",
            label_visibility="collapsed",
            height=90,
        )
        submitted = st.form_submit_button("Ask", use_container_width=False)

    question = ((typed if submitted else "") or pending or "").strip()
    if question:
        st.session_state.chat.append({"role": "user", "kind": "q", "text": question})
        with st.spinner("Looking that up…"):
            _run_question(service, question)
        st.rerun()


def _page_anomalies(service: TicketService) -> None:
    st.markdown('<p class="page-kicker">Anomalies</p>', unsafe_allow_html=True)
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
    st.markdown('<p class="page-kicker">Tickets</p>', unsafe_allow_html=True)
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
    st.set_page_config(
        page_title="Ticket Intelligence",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={"Get Help": None, "Report a bug": None, "About": None},
    )
    _inject_theme()
    service = get_service()
    with st.sidebar:
        st.markdown(
            '<div class="brand"><div class="brand-name">Ticket Intelligence</div>'
            '<div class="brand-sub">Operations console</div></div>',
            unsafe_allow_html=True,
        )
        page = st.radio("Section", PAGES, label_visibility="collapsed")
    if page == "Overview":
        _page_overview(service)
    elif page == "Ask the data":
        _page_ask(service)
    elif page == "Anomalies":
        _page_anomalies(service)
    else:
        _page_tickets(service)


main()
