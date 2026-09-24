import type { Anomaly, ApiError, Health, QueryResult, Stats, Ticket } from "./types";

const base = import.meta.env.VITE_API_BASE_URL ?? "/api";
const token = (import.meta.env.VITE_API_TOKEN ?? "").trim();

function headers(init?: RequestInit): HeadersInit {
  const extra = new Headers(init?.headers);
  extra.set("Content-Type", "application/json");
  if (token) {
    extra.set("Authorization", `Bearer ${token}`);
  }
  return extra;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: headers(init),
  });
  const payload = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok) {
    const message =
      (typeof payload.detail === "string" && payload.detail) ||
      payload.error ||
      `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

export const api = {
  health: () => request<Health>("/health"),
  stats: () => request<Stats>("/stats"),
  anomalies: (method: string, anomalyType: string) =>
    request<{ count: number; method: string; reference_now: string | null; anomalies: Anomaly[] }>(
      `/anomalies?method=${encodeURIComponent(method)}&anomaly_type=${encodeURIComponent(anomalyType)}`,
    ),
  tickets: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<{ count: number; total: number; tickets: Ticket[] }>(`/tickets?${query}`);
  },
  ticket: (id: string) => request<Ticket>(`/tickets/${encodeURIComponent(id)}`),
  query: (question: string) =>
    request<QueryResult>("/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
