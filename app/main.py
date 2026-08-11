from __future__ import annotations

import os
import time

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars

from .agent import LabAgent
from .audit import record_config_change_if_needed, write_audit_event
from .incidents import disable, enable, status
from .logging_config import configure_logging, get_logger
from .metrics import record_error
from .middleware import CorrelationIdMiddleware
from .pii import hash_user_id, summarize_text
from .observability import force_flush_traces, get_prometheus_metrics, init_observability
from .schemas import ChatRequest, ChatResponse
from .tracing import set_current_span_attributes, tracing_enabled

configure_logging()
log = get_logger()
app = FastAPI(title="Day 13 Observability Lab")
app.add_middleware(CorrelationIdMiddleware)
init_observability(app)
agent = LabAgent()


@app.on_event("startup")
async def startup() -> None:
    record_config_change_if_needed()
    log.info(
        "app_started",
        service=os.getenv("APP_NAME", "day13-observability-lab"),
        env=os.getenv("APP_ENV", "dev"),
        correlation_id="system",
        payload={"tracing_enabled": tracing_enabled()},
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    force_flush_traces()


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "tracing_enabled": tracing_enabled(), "incidents": status()}


@app.get("/metrics")
async def metrics() -> Response:
    return get_prometheus_metrics()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    bind_contextvars(
        user_id_hash=hash_user_id(body.user_id),
        session_id=body.session_id,
        feature=body.feature,
        model=agent.model,
        env=os.getenv("APP_ENV", "dev"),
    )
    set_current_span_attributes(
        {
            "correlation_id": request.state.correlation_id,
            "http.route": "/chat",
            "feature": body.feature,
            "llm.model": agent.model,
        }
    )

    request_started = time.perf_counter()
    log.info(
        "request_received",
        service="api",
        payload={"message_preview": summarize_text(body.message)},
    )
    try:
        result = agent.run(
            user_id=body.user_id,
            feature=body.feature,
            session_id=body.session_id,
            message=body.message,
        )
        set_current_span_attributes(
            {
                "prompt_name": result.prompt_name,
                "prompt_label": result.prompt_label,
                "prompt_version": result.prompt_version,
                "rag.result_count": result.rag_result_count,
                "llm.tokens.input": result.tokens_in,
                "llm.tokens.output": result.tokens_out,
                "llm.cost_usd": result.cost_usd,
                "quality.score": result.quality_score,
                "status": "ok",
            }
        )
        if result.output_token_cap is not None:
            set_current_span_attributes(
                {
                    "llm.output_token_cap": result.output_token_cap,
                    "cost.optimization": "output_token_cap",
                }
            )
        log.info(
            "response_sent",
            service="api",
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            quality_score=result.quality_score,
            cost_optimization=(
                "output_token_cap"
                if result.output_token_cap is not None
                else "disabled"
            ),
            output_token_cap=result.output_token_cap,
            payload={"answer_preview": summarize_text(result.answer)},
        )
        return ChatResponse(
            answer=result.answer,
            correlation_id=request.state.correlation_id,
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            quality_score=result.quality_score,
        )
    except Exception as exc:  # pragma: no cover
        error_type = type(exc).__name__
        latency_ms = int((time.perf_counter() - request_started) * 1000)
        record_error(error_type, latency_ms=latency_ms)
        set_current_span_attributes(
            {"status": "error", "error_type": error_type, "latency_ms": latency_ms}
        )
        log.error(
            "request_failed",
            service="api",
            error_type=error_type,
            payload={"detail": str(exc), "message_preview": summarize_text(body.message)},
        )
        raise HTTPException(status_code=500, detail=error_type) from exc


@app.post("/incidents/{name}/enable")
async def enable_incident(request: Request, name: str) -> JSONResponse:
    try:
        enable(name)
        write_audit_event(
            "incident_enabled",
            actor="api",
            target=name,
            correlation_id=request.state.correlation_id,
            details={"incidents": status()},
        )
        log.warning("incident_enabled", service="control", payload={"name": name})
        return JSONResponse({"ok": True, "incidents": status()})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/incidents/{name}/disable")
async def disable_incident(request: Request, name: str) -> JSONResponse:
    try:
        disable(name)
        write_audit_event(
            "incident_disabled",
            actor="api",
            target=name,
            correlation_id=request.state.correlation_id,
            details={"incidents": status()},
        )
        log.warning("incident_disabled", service="control", payload={"name": name})
        return JSONResponse({"ok": True, "incidents": status()})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
