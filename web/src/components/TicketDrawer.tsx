import type { Ticket } from "../types";
import { StatusPill } from "./StatusPill";

type Props = {
  ticket: Ticket;
  onClose: () => void;
};

export function TicketDrawer({ ticket, onClose }: Props) {
  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="drawer"
        role="dialog"
        aria-label={`Ticket ${ticket.ticket_id}`}
        onClick={(event) => event.stopPropagation()}
      >
        <button className="btn btn-ghost" onClick={onClose} type="button">
          Close
        </button>
        <h2 className="page-title" style={{ fontSize: 32, marginTop: 16 }}>
          {ticket.ticket_id}
        </h2>
        <p className="lede">{ticket.issue_summary}</p>
        <dl>
          <dt>Status</dt>
          <dd>
            <StatusPill value={ticket.status} />
          </dd>
          <dt>Priority</dt>
          <dd>
            <StatusPill value={ticket.priority} />
          </dd>
          <dt>Category</dt>
          <dd>{ticket.category}</dd>
          <dt>Agent</dt>
          <dd>{ticket.agent_id}</dd>
          <dt>Created</dt>
          <dd>{ticket.created_at}</dd>
          <dt>Response hours</dt>
          <dd>{ticket.response_time_hrs ?? "—"}</dd>
          <dt>Resolution hours</dt>
          <dd>{ticket.resolution_time_hrs ?? "—"}</dd>
          <dt>Rating</dt>
          <dd>{ticket.customer_rating ?? "—"}</dd>
        </dl>
      </aside>
    </div>
  );
}
