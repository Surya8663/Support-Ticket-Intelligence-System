import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { StatusPill } from "../components/StatusPill";
import { TicketDrawer } from "../components/TicketDrawer";
import type { Ticket } from "../types";

export function Tickets() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const priority = params.get("priority") ?? "";
  const category = params.get("category") ?? "";
  const search = params.get("search") ?? "";
  const [searchDraft, setSearchDraft] = useState(search);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Ticket | null>(null);

  useEffect(() => {
    setSearchDraft(search);
  }, [search]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (searchDraft !== search) update("search", searchDraft);
    }, 250);
    return () => window.clearTimeout(handle);
  }, [searchDraft, search]);

  useEffect(() => {
    api
      .tickets({ status, priority, category, search, limit: 80 })
      .then((payload) => {
        setTickets(payload.tickets);
        setTotal(payload.total);
      })
      .catch((err: Error) => setError(err.message));
  }, [status, priority, category, search]);

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  return (
    <section>
      <h1 className="page-title">Ticket queue</h1>
      <p className="lede">
        {total} tickets match the current filters. Click a row for the full record.
      </p>
      <div className="filters">
        <input
          value={searchDraft}
          placeholder="Search id, agent, or summary"
          aria-label="Search tickets"
          onChange={(event) => setSearchDraft(event.target.value)}
        />
        <select value={status} onChange={(event) => update("status", event.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          <option>Open</option>
          <option>Resolved</option>
          <option>Escalated</option>
        </select>
        <select value={priority} onChange={(event) => update("priority", event.target.value)} aria-label="Priority">
          <option value="">All priorities</option>
          <option>Low</option>
          <option>Medium</option>
          <option>High</option>
          <option>Critical</option>
        </select>
        <select value={category} onChange={(event) => update("category", event.target.value)} aria-label="Category">
          <option value="">All categories</option>
          <option>Billing</option>
          <option>Technical</option>
          <option>General</option>
        </select>
      </div>
      {error ? <div className="banner error">{error}</div> : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Created</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Category</th>
              <th>Agent</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((ticket) => (
              <tr
                key={ticket.ticket_id}
                className="clickable"
                role="button"
                tabIndex={0}
                onClick={() => setSelected(ticket)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setSelected(ticket);
                }}
              >
                <td>{ticket.ticket_id}</td>
                <td>{ticket.created_at}</td>
                <td>
                  <StatusPill value={ticket.status} />
                </td>
                <td>
                  <StatusPill value={ticket.priority} />
                </td>
                <td>{ticket.category}</td>
                <td>{ticket.agent_id}</td>
                <td>{ticket.issue_summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected ? <TicketDrawer ticket={selected} onClose={() => setSelected(null)} /> : null}
    </section>
  );
}
