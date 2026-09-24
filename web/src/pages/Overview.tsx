import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Stats } from "../types";

function BarList({ data }: { data: Record<string, number> }) {
  const max = Math.max(...Object.values(data), 1);
  return (
    <div>
      {Object.entries(data)
        .sort((a, b) => b[1] - a[1])
        .map(([label, value]) => (
          <div className="bar-row" key={label}>
            <span>{label}</span>
            <div className="bar-track" aria-hidden="true">
              <div className="bar-fill" style={{ width: `${(value / max) * 100}%` }} />
            </div>
            <strong>{value}</strong>
          </div>
        ))}
    </div>
  );
}

export function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .stats()
      .then(setStats)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <div className="banner error">{error}</div>;
  if (!stats) return <p>Loading desk snapshot…</p>;

  return (
    <section>
      <h1 className="page-title">Desk snapshot</h1>
      <p className="lede">
        Deterministic counts from SQLite. Click a card to open the matching queue. Dataset clock is{" "}
        {stats.reference_now}.
      </p>
      <div className="grid-4">
        <button className="metric" type="button" onClick={() => navigate("/tickets")}>
          <div className="label">Tickets</div>
          <div className="value">{stats.row_count}</div>
          <div className="hint">Open the full queue</div>
        </button>
        <button className="metric" type="button" onClick={() => navigate("/tickets?status=Open")}>
          <div className="label">Open</div>
          <div className="value">{stats.by_status.Open ?? 0}</div>
          <div className="hint">Status = Open only</div>
        </button>
        <button className="metric" type="button" onClick={() => navigate("/anomalies?type=sla_breach")}>
          <div className="label">SLA breaches</div>
          <div className="value">{stats.anomaly_counts.sla_breach}</div>
          <div className="hint">High/Critical unresolved &gt; 24h</div>
        </button>
        <button className="metric" type="button" onClick={() => navigate("/anomalies?type=resolution_outlier")}>
          <div className="label">Resolution outliers</div>
          <div className="value">{stats.anomaly_counts.resolution_outlier}</div>
          <div className="hint">IQR fences by category</div>
        </button>
      </div>
      <div className="grid-2" style={{ marginTop: 16 }}>
        <article className="panel">
          <h2>By status</h2>
          <BarList data={stats.by_status} />
        </article>
        <article className="panel">
          <h2>By priority</h2>
          <BarList data={stats.by_priority} />
        </article>
        <article className="panel">
          <h2>By category</h2>
          <BarList data={stats.by_category} />
        </article>
        <article className="panel">
          <h2>Resolved-ticket quality</h2>
          <p>Average rating {stats.customer_rating.mean ?? "—"}</p>
          <p>Median resolution {stats.resolution_time_hrs.median ?? "—"}h</p>
          <p>Longest resolution {stats.resolution_time_hrs.max ?? "—"}h</p>
        </article>
      </div>
    </section>
  );
}
