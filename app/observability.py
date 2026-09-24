from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class MetricsRegistry:
    """Process-local counters for the assessment stack. Not a full APM product."""

    started_at: float = field(default_factory=time.time)
    requests_total: int = 0
    errors_total: int = 0
    query_total: int = 0
    query_failures: int = 0
    sql_timeouts: int = 0
    llm_calls: int = 0
    llm_failures: int = 0
    llm_ms_total: float = 0.0
    sql_executions: int = 0
    sql_ms_total: float = 0.0
    _latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_request(self, status_code: int, latency_ms: float, path: str) -> None:
        with self._lock:
            self.requests_total += 1
            self._latencies_ms.append(latency_ms)
            if status_code >= 400:
                self.errors_total += 1
            if path.rstrip("/").endswith("query"):
                self.query_total += 1
                if status_code >= 400:
                    self.query_failures += 1

    def record_llm(self, latency_ms: float, failed: bool = False) -> None:
        with self._lock:
            self.llm_calls += 1
            self.llm_ms_total += latency_ms
            if failed:
                self.llm_failures += 1

    def record_sql(self, latency_ms: float, timed_out: bool = False) -> None:
        with self._lock:
            self.sql_executions += 1
            self.sql_ms_total += latency_ms
            if timed_out:
                self.sql_timeouts += 1

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._latencies_ms)
            llm_calls = self.llm_calls
            sql_executions = self.sql_executions
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "query_total": self.query_total,
                "query_failures": self.query_failures,
                "sql_timeouts": self.sql_timeouts,
                "sql_executions": sql_executions,
                "llm_calls": llm_calls,
                "llm_failures": self.llm_failures,
                "avg_request_ms": round(sum(samples) / len(samples), 2) if samples else 0.0,
                "avg_llm_ms": round(self.llm_ms_total / llm_calls, 2) if llm_calls else 0.0,
                "avg_sql_ms": round(self.sql_ms_total / sql_executions, 2) if sql_executions else 0.0,
            }


metrics = MetricsRegistry()
