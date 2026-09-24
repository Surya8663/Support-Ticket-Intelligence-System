import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { StatusPill } from "../components/StatusPill";
import { TicketDrawer } from "../components/TicketDrawer";
import type { Anomaly, Ticket } from "../types";

export function Anomalies() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const method = params.get("method") ?? "iqr";
  const type = params.get("type") ?? "all";
  const [rows, setRows] = useState<Anomaly[]>([]);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Ticket | null>(null);

  useEffect(() => {
    api
      .anomalies(method, type)
      .then((payload) => {
        setRows(payload.anomalies);
        setCount(payload.count);
      })
      .catch((err: Error) => setError(err.message));
  }, [method, type]);

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next);
  }

  async function openTicket(id: string) {
    try {
      setSelected(await api.ticket(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ticket lookup failed");
    }
  }

  return (
    <section>
      <h1 className="page-title">Anomalies</h1>
      <p className="lede">
        {count} flags. Detection is statistical. Open a row to inspect the underlying ticket.
      </p>
      <div className="filters">
        <select value={method} onChange={(event) => update("method", event.target.value)} aria-label="Method">
          <option value="iqr">IQR</option>
          <option value="zscore">Z-score</option>
        </select>
        <select value={type} onChange={(event) => update("type", event.target.value)} aria-label="Type">
          <option value="all">All types</option>
          <option value="resolution_outlier">Resolution outliers</option>
          <option value="sla_breach">SLA breaches</option>
        </select>
        <button className="btn btn-ghost" type="button" onClick={() => navigate("/tickets")}>
          Open ticket queue
        </button>
      </div>
      {error ? <div className="banner error">{error}</div> : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Type</th>
              <th>Value</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${row.ticket_id}-${row.anomaly_type}`}
                className="clickable"
                role="button"
                tabIndex={0}
                onClick={() => void openTicket(row.ticket_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void openTicket(row.ticket_id);
                }}
              >
                <td>{row.ticket_id}</td>
                <td>{row.anomaly_type}</td>
                <td>{row.metric_value ?? "—"}</td>
                <td>
                  <StatusPill value={row.priority} />
                </td>
                <td>
                  <StatusPill value={row.status} />
                </td>
                <td>{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected ? <TicketDrawer ticket={selected} onClose={() => setSelected(null)} /> : null}
    </section>
  );
}
