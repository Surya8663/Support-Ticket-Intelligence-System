from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.llm.groq_client import GroqNotConfiguredError, GroqRequestError
from app.models.schemas import (
    AnomaliesResponse,
    ErrorResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    StatsResponse,
    TicketListResponse,
    TicketOut,
)
from app.nlquery.sql_guard import SQLGuardError
from app.nlquery.text_to_sql import QueryTranslationError
from app.services.ticket_service import TicketService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    service = TicketService(settings)
    service.startup()
    app.state.settings = settings
    app.state.service = service
    yield


app = FastAPI(
    title="Support Ticket Intelligence System",
    description="NL query + anomaly detection over support tickets.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "method=%s path=%s status=%s latency_ms=%.1f llm=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request.url.path.startswith("/query"),
    )
    return response


def _service() -> TicketService:
    return app.state.service


@app.get("/health", response_model=HealthResponse)
def health():
    return _service().health()


@app.get("/stats", response_model=StatsResponse)
def stats():
    return _service().stats()


@app.get("/anomalies", response_model=AnomaliesResponse)
def anomalies(
    method: Literal["iqr", "zscore"] = Query(default="iqr"),
    anomaly_type: Literal["all", "resolution_outlier", "sla_breach"] = Query(default="all"),
    iqr_multiplier: float | None = Query(default=None, gt=0),
    zscore_threshold: float | None = Query(default=None, gt=0),
    sla_breach_hours: float | None = Query(default=None, gt=0),
):
    return _service().anomalies(
        method=method,
        anomaly_type=anomaly_type,
        iqr_multiplier=iqr_multiplier,
        zscore_threshold=zscore_threshold,
        sla_breach_hours=sla_breach_hours,
    )


@app.get("/tickets", response_model=TicketListResponse)
def list_tickets(
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _service().list_tickets(
        status=status,
        priority=priority,
        category=category,
        agent_id=agent_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@app.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str):
    ticket = _service().get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error="not_found", detail=f"{ticket_id} was not found.").model_dump(),
        )
    return ticket


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest):
    return _service().query(payload.question)


@app.exception_handler(GroqNotConfiguredError)
async def groq_missing(_, exc: GroqNotConfiguredError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(error="llm_not_configured", detail=str(exc)).model_dump(),
    )


@app.exception_handler(GroqRequestError)
async def groq_failed(_, exc: GroqRequestError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(error="llm_unavailable", detail=str(exc)).model_dump(),
    )


@app.exception_handler(QueryTranslationError)
async def unprocessable_query(_, exc: QueryTranslationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error="unprocessable_query", detail=str(exc)).model_dump(),
    )


@app.exception_handler(SQLGuardError)
async def rejected_sql(_, exc: SQLGuardError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error="unsafe_sql", detail=str(exc)).model_dump(),
    )


@app.exception_handler(sqlite3.Error)
async def sql_execute_failed(_, exc: sqlite3.Error):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error="sql_execution_failed", detail=str(exc)).model_dump(),
    )


@app.exception_handler(FileNotFoundError)
async def missing_file(_, exc: FileNotFoundError):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="data_missing", detail=str(exc)).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(error="invalid_request", detail=str(exc.errors())).model_dump(),
    )
