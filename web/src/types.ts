export type Health = {
  status: string;
  database: string;
  groq_configured: boolean;
  row_count: number;
  reference_now: string | null;
};

export type NumericSummary = {
  count: number;
  mean: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
};

export type Stats = {
  row_count: number;
  reference_now: string | null;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_category: Record<string, number>;
  by_agent: Record<string, number>;
  resolution_time_hrs: NumericSummary;
  customer_rating: NumericSummary;
  anomaly_counts: { resolution_outlier: number; sla_breach: number };
};

export type Ticket = {
  ticket_id: string;
  created_at: string;
  category: string;
  priority: string;
  status: string;
  response_time_hrs: number | null;
  resolution_time_hrs: number | null;
  agent_id: string;
  customer_rating: number | null;
  issue_summary: string;
};

export type Anomaly = {
  ticket_id: string;
  anomaly_type: "resolution_outlier" | "sla_breach";
  metric_name: string;
  metric_value: number | null;
  threshold: number | null;
  reason: string;
  created_at: string;
  category: string;
  priority: string;
  status: string;
};

export type QueryResult = {
  question: string;
  answer: string;
  sql: string;
  explanation: string;
  row_count: number;
  rows: Record<string, unknown>[];
};

export type ApiError = {
  error?: string;
  detail?: string;
};
