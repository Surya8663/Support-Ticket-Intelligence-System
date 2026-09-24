# Support Ticket Intelligence System

DOTMappers AI Engineer assessment — an end-to-end system that ingests `support_tickets.csv`, answers natural-language questions, flags anomalies, and exposes both a REST API and a UI.

The LLM is a **translation layer, not a compute engine**. Groq turns a question into SQLite and turns rows back into prose. Counts, averages, filters, and anomaly scores are computed in deterministic code so numbers do not hallucinate.

## Quick start

Get a free Groq key at [console.groq.com](https://console.groq.com) (needed only for `POST /query`). `/health`, `/stats`, and `/anomalies` run without it.

### Docker (single command)

```bash
copy .env.example .env
# add GROQ_API_KEY to .env
docker compose up --build
```

- API: http://127.0.0.1:8000/docs
- UI: http://127.0.0.1:5173

Compose reads `GROQ_API_KEY` from a local `.env` if present. The stack still starts without a key; NL query returns HTTP 503.

### Local (two terminals)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

```bash
uvicorn app.main:app --reload
```

```bash
cd web
npm install
npm run dev
```

The Vite dev server proxies API calls to `http://127.0.0.1:8000`.

```bash
python -m pytest tests -q
```

## Architecture

```
support_tickets.csv
        │ ingest + validate + type-coerce
        ▼
   SQLite (tickets + anomalies)
        │
        ├─ NL Query Engine
        │    Groq JSON (text-to-SQL)
        │    → sqlparse guard (SELECT-only, table allow-list)
        │    → read-only SQLite
        │    → Groq JSON summary
        │
        └─ Anomaly Engine (no LLM)
             IQR on resolution_time_hrs (per category)
             SLA: unresolved High/Critical older than 24h
        │
        ▼
   FastAPI  /health  /query  /anomalies  /stats  /tickets
        │
        ▼
   React console (HTTP client only — no duplicated business logic)
```

**Why this shape**

- The PDF schema preview uses aliases (`resol_time_hrs`, `cust_rating`). The real file uses `resolution_time_hrs` and `customer_rating`. Schema is introspected at runtime from the loaded CSV/SQLite, so prompts follow the file, not the brief.
- The dataset is Q1 2024 (`created_at` from `2024-01-01 08:54` to `2024-03-30 18:06`). “This month” / “this week” use that `MAX(created_at)` as *now*. A wall-clock date in 2026 would return zero rows.
- Resolution times are right-skewed (median 12h, max 119.7h). IQR is the default because it is more robust than z-score on that distribution.
- Unresolved tickets have null `resolution_time_hrs` and `customer_rating` (173 rows, 1:1 with Open/Escalated). Those nulls are domain-meaningful and are never imputed.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB ping + whether a Groq key is configured. No LLM call. |
| POST | `/query` | `{"question": "..."}` → answer, SQL, row count, capped rows |
| GET | `/anomalies` | `method=iqr\|zscore`, `anomaly_type=all\|resolution_outlier\|sla_breach` |
| GET | `/stats` | Counts by status / priority / category / agent |
| GET | `/tickets` | Filterable ticket queue (`status`, `priority`, `category`, `search`) |
| GET | `/tickets/{id}` | Single ticket record |

Errors are JSON `{"error": "...", "detail": "..."}`:

- `400` invalid request
- `422` unsafe or unexecutable SQL
- `503` Groq missing or upstream failure

## Example outputs (run against this CSV)

`GET /health`

```json
{
  "status": "ok",
  "database": "connected",
  "groq_configured": false,
  "row_count": 500,
  "reference_now": "2024-03-30 18:06:00"
}
```

`GET /stats` (excerpt)

```json
{
  "by_status": {"Resolved": 327, "Open": 111, "Escalated": 62},
  "anomaly_counts": {"resolution_outlier": 22, "sla_breach": 80},
  "resolution_time_hrs": {"count": 327, "mean": 19.158, "median": 12.0, "max": 119.7}
}
```

`GET /anomalies?anomaly_type=sla_breach` returns **80** High/Critical tickets still Open or Escalated and older than 24 hours versus `2024-03-30 18:06:00`.

### Sample NL questions

Relative dates are bound to `reference_now = 2024-03-30 18:06:00`. The SQL below is what the guard will execute; Groq writes the prose around these numbers when a key is set.

**1. "How many tickets are currently open?"**

```sql
SELECT COUNT(*) AS open_tickets FROM tickets WHERE status = 'Open'
```

Answer: **111**

**2. "Which agent resolved the most tickets this month?"**

```sql
SELECT agent_id, COUNT(*) AS resolved_count
FROM tickets
WHERE status = 'Resolved' AND strftime('%Y-%m', created_at) = '2024-03'
GROUP BY agent_id
ORDER BY resolved_count DESC
LIMIT 1
```

Answer: **AGT-01** with **16** resolved tickets in March 2024.

**3. "Show me all Critical tickets not resolved within 12 hours."**

```sql
SELECT ticket_id, status, resolution_time_hrs,
       (julianday('2024-03-30 18:06:00') - julianday(created_at)) * 24.0 AS age_hours
FROM tickets
WHERE priority = 'Critical'
  AND (
        (status = 'Resolved' AND resolution_time_hrs > 12)
     OR (status IN ('Open', 'Escalated')
         AND (julianday('2024-03-30 18:06:00') - julianday(created_at)) * 24.0 > 12)
  )
```

Answer: **34** tickets.

**4. "What is the average customer rating for Technical category tickets?"**

```sql
SELECT AVG(customer_rating) AS avg_rating
FROM tickets
WHERE category = 'Technical'
```

Answer: **3.74** across **104** rated (resolved) Technical tickets. Unresolved tickets are excluded because rating is NULL.

**5. "Are there any anomalies in resolution times this week?"**

```sql
SELECT ticket_id, metric_value, created_at, reason
FROM anomalies
WHERE anomaly_type = 'resolution_outlier'
  AND created_at >= '2024-03-23 18:06:00'
  AND created_at <= '2024-03-30 18:06:00'
ORDER BY metric_value DESC
```

Answer: **yes — 6** IQR outliers this week, including TKT-108 (119.7h) and TKT-130 (114.3h).

## Configuration

All thresholds live in `.env` / `app/config.py`. Nothing about the 500-row file is hardcoded into prompts as sample answers.

| Variable | Default | Role |
|---|---|---|
| `GROQ_API_KEY` | empty | Required for `/query` |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Must be a model your Groq key can access; Llama IDs are not on every free-tier account |
| `IQR_MULTIPLIER` | `1.5` | Tukey fence |
| `ZSCORE_THRESHOLD` | `3.0` | Optional `/anomalies?method=zscore` |
| `SLA_BREACH_HOURS` | `24` | Unresolved High/Critical age |

## Project layout

```
app/
  main.py                 FastAPI + lifespan ingest
  config.py               pydantic-settings
  ingestion/              CSV → SQLite, runtime schema
  nlquery/                prompts, text-to-SQL, SQL guard, summarizer
  anomalies/              IQR + SLA detector
  services/               shared orchestration
  llm/                    Groq client (retries, JSON mode)
web/                      React operations console (light theme)
tests/                    guard, detector, ingest, API
data/support_tickets.csv
```

## Known limitations

- Text-to-SQL is probabilistic. Complex wording can need the one-retry path. Generated SQL is always returned so a wrong query is visible.
- IQR / 24h SLA defaults are statistical, not DOTMappers’ real policy. They are config, not hidden constants.
- Groq free-tier rate limits are not queued. Under load, `/query` would need a worker — out of scope for 24 hours.
- No auth or multi-tenancy.
- Optional LLM explanations of each anomaly were not added; detection never depends on Groq.

## Walkthrough talking points

1. The LLM translates; SQLite and statistics compute. That is why the open-ticket count is 111, not a guessed paragraph.
2. Schema is introspected. The PDF column aliases were wrong; the system follows the CSV.
3. “Now” is `max(created_at)` because the file is Q1 2024.
4. SQL guard + a read-only SQLite URI is defense in depth.
5. 80 SLA breaches and 22 IQR outliers are reproducible without an API key.
6. With more time: Ollama fallback, query cache, auth, and a Groq queue.

## Submission

Repository: https://github.com/Surya8663/Support-Ticket-Intelligence-System
