"""
FastAPI APIRouter containing endpoint definitions for the BI Agent API.
Orchestrates HTTP requests with pre-cached backend services.
"""

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from models.schemas import (
    AskRequest,
    AskResponse,
    DataMetadata,
    HealthResponse,
    LeadershipReportResponse,
    MetricsResponse,
    ReadyResponse,
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
    summary="Liveness Health Check",
    description="Reports process liveness to verify the backend server is running.",
)
async def health_check() -> HealthResponse:
    """Liveness probe: returns 200 OK as long as the process is alive."""
    return HealthResponse(status="healthy")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness Health Check",
    description="Indicates whether business dataset is loaded and ready for operations.",
)
async def readiness_check(
    response: Response,
    state: Any = Depends(get_app_state),
) -> ReadyResponse:
    """
    Readiness probe:
    Returns 200 if data is usable ('live' or 'fallback').
    Returns 503 if data is 'unavailable'.
    """
    data_status = getattr(state, "data_status", "unavailable")
    data_source = getattr(state, "data_source", "unavailable")
    loaded_at = getattr(state, "loaded_at", None)
    fallback_reason = getattr(state, "fallback_reason", None)

    if data_status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(
            status="not_ready",
            data_source=data_source,
            data_status=data_status,
            loaded_at=loaded_at,
            fallback_reason=fallback_reason or "DATA_SOURCES_UNAVAILABLE",
        )

    return ReadyResponse(
        status="ready",
        data_source=data_source,
        data_status=data_status,
        loaded_at=loaded_at,
        fallback_reason=fallback_reason,
    )


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness Health Check (Alias)",
    description="Alias for /ready for orchestrators checking /health/ready.",
)
async def readiness_check_alias(
    response: Response,
    state: Any = Depends(get_app_state),
) -> ReadyResponse:
    """Alias for readiness check."""
    return await readiness_check(response=response, state=state)


@router.get(
    "/data-status",
    response_model=DataMetadata,
    summary="Data Source Metadata",
    description="Returns data source origin (monday_api, excel_fallback, or unavailable), status, timestamp, and fallback reason.",
)
async def get_data_status(state: Any = Depends(get_app_state)) -> DataMetadata:
    """Check dataset source metadata."""
    meta = getattr(
        state,
        "data_metadata",
        {
            "data_source": "unavailable",
            "data_status": "unavailable",
            "last_updated_at": None,
            "fallback_reason": "Not initialized",
        },
    )
    if isinstance(meta, dict):
        return DataMetadata(**meta)
    return meta


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Dashboard Metrics",
    description="Retrieves pre-computed, in-memory cached business intelligence metrics.",
)
async def get_cached_metrics(state: Any = Depends(get_app_state)) -> MetricsResponse:
    """Return in-memory cached business dashboard metrics without recalculating."""
    logger.info("Handling GET /metrics request.")
    data_status = getattr(state, "data_status", "live")
    if data_status == "unavailable":
        reason = getattr(state, "fallback_reason", "No usable dataset available.")
        logger.error("GET /metrics rejected: Dataset unavailable. %s", reason)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No usable dataset available. {reason}",
        )

    cached_metrics = getattr(state, "dashboard_metrics", None)
    if cached_metrics is None:
        logger.error("Dashboard metrics not initialized in app state.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard metrics have not been initialized.",
        )

    raw_meta = getattr(state, "data_metadata", None)
    meta = DataMetadata(**raw_meta) if isinstance(raw_meta, dict) else raw_meta
    return MetricsResponse(dashboard_metrics=cached_metrics, data_metadata=meta)


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

    data_status = getattr(state, "data_status", "live")
    if data_status == "unavailable":
        reason = getattr(state, "fallback_reason", "No usable dataset available.")
        logger.error("POST /ask rejected: Dataset unavailable. %s", reason)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"BI Agent analysis unavailable: No usable dataset could be loaded. {reason}",
        )

    bi_agent = getattr(state, "bi_agent", None)
    if bi_agent is None:
        logger.error("BIAgent not initialized (missing API key or startup failure).")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BI Agent service is unavailable. Please verify GROQ_API_KEY configuration.",
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

    data_status = getattr(state, "data_status", "live")
    if data_status == "unavailable":
        reason = getattr(state, "fallback_reason", "No usable dataset available.")
        logger.error("GET /leadership-report rejected: Dataset unavailable. %s", reason)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Leadership report unavailable: No usable dataset could be loaded. {reason}",
        )

    bi_agent = getattr(state, "bi_agent", None)
    if bi_agent is None:
        logger.error("BIAgent not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BI Agent service is unavailable. Please verify GROQ_API_KEY configuration.",
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
