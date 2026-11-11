"""
Dedicated Public Demo API Routes for Skylarp Drones Portfolio Mode.

These endpoints:
- Expose synthetic portfolio data only.
- Do NOT invoke tenant context or authentication dependencies.
- Enforce strict input validation and sliding-window in-memory IP rate limiting.
- Never leak server-side secrets, database details, or real tenant information.
"""

from collections import defaultdict
from datetime import datetime, timezone
import ipaddress
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from models.schemas import (
    AskResponse,
    DataMetadata,
    LeadershipReportResponse,
    MetricsResponse,
)
from services.demo_data import generate_deterministic_demo_answer

logger = logging.getLogger(__name__)

demo_router = APIRouter(prefix="/demo", tags=["Demo Mode"])


# -------------------------------------------------------------------------
# Request Models
# -------------------------------------------------------------------------
class DemoAskRequest(BaseModel):
    """Validated question payload for public demo AI assistant."""
    question: str = Field(
        ...,
        min_length=2,
        max_length=250,
        description="Business query about synthetic drone inspection data (max 250 characters).",
    )


# -------------------------------------------------------------------------
# Trusted Proxy & In-Memory Sliding-Window Rate Limiter
# -------------------------------------------------------------------------
# Documentation of Limitations:
# 1. This rate limiter is strictly an IN-MEMORY mechanism per process instance.
#    It does not coordinate state across distributed multi-container or multi-worker deployments.
# 2. X-Forwarded-For is only parsed if the immediate peer IP matches configured TRUSTED_PROXIES.
#    Arbitrary, unverified X-Forwarded-For headers are NEVER trusted.
# -------------------------------------------------------------------------

class InMemoryRateLimiter:
    """Sliding-window rate limiter per client IP."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        # Prune timestamps outside current sliding window
        valid_timestamps = [ts for ts in self.requests[client_ip] if ts > window_start]
        self.requests[client_ip] = valid_timestamps

        if len(valid_timestamps) >= self.max_requests:
            return False

        self.requests[client_ip].append(now)
        return True


demo_ask_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)


def extract_client_ip(request: Request) -> str:
    """
    Extract client IP with safe trusted-proxy validation.
    
    Walks the forwarded chain from the rightmost (most recent proxy) hop,
    trusting only hops that match TRUSTED_PROXIES.
    """
    peer_ip = request.client.host if request.client else "unknown"
    if peer_ip == "unknown":
        return "unknown"

    trusted_proxies_cfg = os.getenv("TRUSTED_PROXIES", "").strip()
    if not trusted_proxies_cfg:
        # No proxies trusted - use direct peer connection IP only
        return peer_ip

    trusted_networks = []
    for item in trusted_proxies_cfg.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            trusted_networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            pass

    def is_trusted(ip_str: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(ip_str.strip())
            return any(ip_obj in net for net in trusted_networks)
        except ValueError:
            return False

    # If immediate peer is not a trusted proxy, ignore X-Forwarded-For completely
    if not is_trusted(peer_ip):
        return peer_ip

    xff = request.headers.get("X-Forwarded-For")
    if not xff:
        return peer_ip

    # Walk backwards from the rightmost hop (closest to our trusted proxy)
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    for hop in reversed(hops):
        if not is_trusted(hop):
            return hop

    return peer_ip


def verify_demo_mode_enabled(request: Request) -> None:
    """Verify backend has DEMO_MODE explicitly enabled."""
    is_demo = getattr(request.app.state, "demo_mode_enabled", False)
    if not is_demo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo endpoints are not available on this server.",
        )


# -------------------------------------------------------------------------
# Demo API Endpoints
# -------------------------------------------------------------------------

@demo_router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Demo Dashboard Metrics",
    description="Returns precomputed synthetic business intelligence metrics for public portfolio demonstration.",
)
async def get_demo_metrics(
    request: Request,
    response: Response,
    _: None = Depends(verify_demo_mode_enabled),
) -> MetricsResponse:
    """Return precomputed synthetic demonstration metrics without authentication."""
    demo_metrics = getattr(request.app.state, "demo_metrics", None)
    if not demo_metrics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Synthetic demo dataset is currently unavailable.",
        )

    meta = getattr(request.app.state, "demo_metadata", {})
    response.headers["Cache-Control"] = "public, max-age=300"
    return MetricsResponse(
        dashboard_metrics=demo_metrics,
        data_metadata=DataMetadata(**meta),
    )


@demo_router.get(
    "/data-status",
    response_model=DataMetadata,
    summary="Demo Data Status",
    description="Returns synthetic dataset metadata for portfolio demonstration.",
)
async def get_demo_data_status(
    request: Request,
    _: None = Depends(verify_demo_mode_enabled),
) -> DataMetadata:
    """Return synthetic dataset metadata."""
    meta = getattr(request.app.state, "demo_metadata", None)
    if not meta:
        return DataMetadata(
            data_source="synthetic_demo",
            data_status="unavailable",
            last_updated_at=None,
            fallback_reason="Synthetic demo dataset not initialized.",
        )
    return DataMetadata(**meta)


@demo_router.post(
    "/ask",
    response_model=AskResponse,
    summary="Demo AI BI Assistant",
    description="Ask executive business questions against synthetic drone data with rate limiting.",
)
async def ask_demo_question(
    payload: DemoAskRequest,
    request: Request,
    _: None = Depends(verify_demo_mode_enabled),
) -> AskResponse:
    """Public rate-limited AI question answering for portfolio demo."""
    client_ip = extract_client_ip(request)

    # 1. Enforce in-memory sliding-window rate limit (5 req/min per IP)
    if not demo_ask_limiter.is_allowed(client_ip):
        logger.warning("Demo /ask rate limit exceeded for client IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: 5 questions per minute limit for demo mode.",
        )

    demo_metrics = getattr(request.app.state, "demo_metrics", None)
    demo_dataset = getattr(request.app.state, "demo_dataset", None)

    if not demo_metrics or not demo_dataset:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo analytics context is unavailable.",
        )

    clean_deals_df, clean_wo_df, quality_report = demo_dataset
    demo_bi_agent = getattr(request.app.state, "demo_bi_agent", None)

    # 2. Try Groq AI Agent if initialized
    answer_text = None
    if demo_bi_agent is not None:
        try:
            res = demo_bi_agent.answer_question(
                question=payload.question,
                deals_df=clean_deals_df,
                wo_df=clean_wo_df,
                quality_report=quality_report,
            )
            raw_answer = res.get("answer")
            if raw_answer and not any(k in raw_answer for k in ["Error", "unavailable", "quota"]):
                answer_text = raw_answer
        except Exception as e:
            logger.warning("Demo Groq AI query failed (%s); switching to deterministic demo answer.", e)

    # 3. Fall back to deterministic, factually grounded answers from demo metrics
    if not answer_text:
        answer_text = generate_deterministic_demo_answer(payload.question, demo_metrics)

    caveats = quality_report.get("caveats", []) if quality_report else []
    return AskResponse(
        answer=answer_text,
        dashboard_metrics=demo_metrics,
        data_quality_notes=caveats,
    )


@demo_router.get(
    "/leadership-report",
    response_model=LeadershipReportResponse,
    summary="Demo Leadership Report",
    description="Returns an executive leadership report generated from synthetic demo data.",
)
async def get_demo_leadership_report(
    request: Request,
    _: None = Depends(verify_demo_mode_enabled),
) -> LeadershipReportResponse:
    """Return executive leadership report for demo mode."""
    demo_dataset = getattr(request.app.state, "demo_dataset", None)
    demo_metrics = getattr(request.app.state, "demo_metrics", None)

    if not demo_dataset or not demo_metrics:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo dataset unavailable.",
        )

    clean_deals_df, clean_wo_df, quality_report = demo_dataset
    demo_bi_agent = getattr(request.app.state, "demo_bi_agent", None)

    report_text = None
    if demo_bi_agent is not None:
        try:
            res = demo_bi_agent.generate_leadership_report(
                deals_df=clean_deals_df,
                wo_df=clean_wo_df,
                quality_report=quality_report,
            )
            raw_report = res.get("report")
            if raw_report and "Error" not in raw_report:
                report_text = raw_report
        except Exception as e:
            logger.warning("Groq report generation failed (%s); using deterministic template.", e)

    if not report_text:
        pipeline = demo_metrics.get("pipeline_summary", {})
        billing = demo_metrics.get("billing_summary", {})
        wo_summary = demo_metrics.get("work_order_summary", {})
        report_text = (
            "# Executive Leadership Report (Portfolio Demonstration)\n\n"
            "## Executive Summary\n"
            f"The commercial drone inspection operations demonstrate robust commercial momentum. Total sales pipeline value is **${pipeline.get('total_pipeline_value', 0):,.2f}** with a weighted value of **${pipeline.get('weighted_pipeline_value', 0):,.2f}**.\n\n"
            "## Sales Pipeline Health\n"
            f"A total of **{pipeline.get('total_deals', 0)}** commercial opportunities are tracked across solar, agricultural, and civil infrastructure inspection verticals.\n\n"
            "## Operational Performance\n"
            f"Execution teams have completed **{wo_summary.get('completed', 0)}** aerial sorties with **{wo_summary.get('in_progress', 0)}** sorties actively underway.\n\n"
            "## Billing Overview\n"
            f"Total invoiced billings stand at **${billing.get('total_invoiced', 0):,.2f}** with a healthy collection efficiency of **{billing.get('collection_rate', 0):.1f}%**.\n\n"
            "## Recommended Actions\n"
            "1. Accelerate delivery on in-progress inspection sorties to convert WIP into recognized billings.\n"
            "2. Capitalize on high win-rate segments in renewable solar inspection by expanding regional flight capacity.\n\n"
            "## Data Quality Notes\n"
            "*Notice: This report was deterministically generated for public portfolio demonstration using synthetic data.*"
        )

    return LeadershipReportResponse(
        report=report_text,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
