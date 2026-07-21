"""
FastAPI APIRouter containing endpoint definitions for the BI Agent API.
Orchestrates HTTP requests with pre-cached backend services.
"""

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status

from models.schemas import (
    AskRequest,
    AskResponse,
    HealthResponse,
    LeadershipReportResponse,
    MetricsResponse,
    RootResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_state(request: Request) -> Any:
    """Dependency helper to access application state."""
    return request.app.state


@router.get(
    "/",
    response_model=RootResponse,
    summary="Root Endpoint",
    description="Returns welcome message for the Business Intelligence Agent API.",
)
async def root() -> dict[str, str]:
    """Root endpoint welcome message."""
    return {"message": "Business Intelligence Agent API"}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Checks the operational health status of the API service.",
)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy")


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Dashboard Metrics",
    description="Retrieves pre-computed, in-memory cached business intelligence metrics.",
)
async def get_cached_metrics(state: Any = Depends(get_app_state)) -> MetricsResponse:
    """Return in-memory cached business dashboard metrics without recalculating."""
    logger.info("Handling GET /metrics request.")
    cached_metrics = getattr(state, "dashboard_metrics", None)
    if cached_metrics is None:
        logger.error("Dashboard metrics not initialized in app state.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard metrics have not been initialized.",
        )
    return MetricsResponse(dashboard_metrics=cached_metrics)


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask Business Intelligence Agent",
    description="Ask strategic business questions to the AI Business Intelligence Agent based on pre-computed metrics.",
)
async def ask_question(
    payload: AskRequest, state: Any = Depends(get_app_state)
) -> AskResponse:
    """Ask strategic executive business question."""
    logger.info("Handling POST /ask request with question: '%s'", payload.question)

    bi_agent = getattr(state, "bi_agent", None)
    if bi_agent is None:
        logger.error("BIAgent not initialized (missing API key or startup failure).")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BI Agent service is unavailable. Please verify OPENAI_API_KEY configuration.",
        )

    deals_df = getattr(state, "deals_df", None)
    wo_df = getattr(state, "wo_df", None)
    quality_report = getattr(state, "quality_report", {})

    try:
        res = bi_agent.answer_question(
            question=payload.question,
            deals_df=deals_df,
            wo_df=wo_df,
            quality_report=quality_report,
        )
        return AskResponse(
            answer=res.get("answer", ""),
            dashboard_metrics=res.get("dashboard_metrics", {}),
            data_quality_notes=res.get("data_quality_notes", []),
        )
    except Exception as e:
        logger.exception("Error executing BIAgent.answer_question: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while generating analysis: {str(e)}",
        )


@router.get(
    "/leadership-report",
    response_model=LeadershipReportResponse,
    summary="Generate Executive Leadership Report",
    description="Generates a comprehensive executive leadership report formatted in Markdown.",
)
async def get_leadership_report(
    state: Any = Depends(get_app_state)
) -> LeadershipReportResponse:
    """Generate executive leadership report in Markdown."""
    logger.info("Handling GET /leadership-report request.")

    bi_agent = getattr(state, "bi_agent", None)
    if bi_agent is None:
        logger.error("BIAgent not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BI Agent service is unavailable. Please verify OPENAI_API_KEY configuration.",
        )

    deals_df = getattr(state, "deals_df", None)
    wo_df = getattr(state, "wo_df", None)
    quality_report = getattr(state, "quality_report", {})

    try:
        res = bi_agent.generate_leadership_report(
            deals_df=deals_df, wo_df=wo_df, quality_report=quality_report
        )
        return LeadershipReportResponse(
            report=res.get("report", ""),
            generated_at=res.get("generated_at", ""),
        )
    except Exception as e:
        logger.exception("Error executing BIAgent.generate_leadership_report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while generating executive report: {str(e)}",
        )
