import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Health } from "../types";

export function Layout() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <p className="brand-kicker">Operations console</p>
        <h1 className="brand">Ticket Intelligence</h1>
        <nav className="nav" aria-label="Primary">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/ask">Ask the data</NavLink>
          <NavLink to="/anomalies">Anomalies</NavLink>
          <NavLink to="/tickets">Ticket queue</NavLink>
        </nav>
        <div className="sidebar-meta">
          {error ? (
            <p>API unreachable. Start FastAPI on port 8000.</p>
          ) : (
            <>
              <p>{health?.row_count ?? "—"} tickets loaded</p>
              <p>Dataset now {health?.reference_now ?? "—"}</p>
              <p>{health?.groq_configured ? "Groq connected" : "Groq key missing"}</p>
            </>
          )}
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
