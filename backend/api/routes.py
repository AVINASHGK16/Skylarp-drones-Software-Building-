"""
FastAPI APIRouter containing endpoint definitions for the BI Agent API.
Orchestrates HTTP requests with pre-cached backend services.
"""

import logging
from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.snapshot import SnapshotMetadata
from db.models.tenant import TenantMembership, User
from db.session import get_db_session, set_session_tenant_context, set_session_user_context
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
from services.crypto_service import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


class AuthenticatedTenantContext:
    """Authenticated user context with verified active tenant membership."""

    def __init__(self, user: User, membership: TenantMembership):
        self.user = user
        self.membership = membership
        self.tenant_id = membership.tenant_id
        self.user_id = user.user_id
        self.role = membership.role


async def get_authenticated_tenant_context(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedTenantContext:
    """
    Authenticate user via Bearer JWT and verify their active membership in the requested tenant.
    
    Security Guarantees:
    1. Rejects unauthenticated requests with 401 Unauthorized (no default tenant fallback).
    2. Never trusts X-Tenant-ID alone: X-Tenant-ID is only a selection hint among the user's verified active memberships.
    3. Live database verification: checks user.is_active and membership.is_active on every request.
    4. Immediately rejects revoked memberships or deactivated accounts with 403/401 even if JWT is unexpired.
    5. Sets PostgreSQL transaction-local tenant context (app.current_tenant_id) for RLS enforcement.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided or are malformed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token payload.",
        )

    try:
        user_uuid = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user ID in token.")

    # 1. Fetch user from DB and verify active status
    user_res = await session.execute(select(User).where(User.user_id == user_uuid))
    user = user_res.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated or does not exist.",
        )

    # 2. Determine requested tenant
    requested_tenant_id = None
    x_tenant_header = request.headers.get("X-Tenant-ID")
    if x_tenant_header:
        try:
            requested_tenant_id = uuid.UUID(x_tenant_header.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid X-Tenant-ID header format: {x_tenant_header}",
            )

    if requested_tenant_id is None and payload.get("tenant_id"):
        try:
            requested_tenant_id = uuid.UUID(payload["tenant_id"])
        except ValueError:
            pass

    # 3. Query active memberships for this user
    await set_session_user_context(session, user_uuid)
    mems_res = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_uuid,
            TenantMembership.is_active == True,
        )
    )
    active_memberships = mems_res.scalars().all()

    if not active_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an active membership in any organization.",
        )

    target_membership = None
    if requested_tenant_id is not None:
        for m in active_memberships:
            if m.tenant_id == requested_tenant_id:
                target_membership = m
                break
        if target_membership is None:
            # Check if membership exists but is deactivated
            inactive_res = await session.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == user_uuid,
                    TenantMembership.tenant_id == requested_tenant_id,
                )
            )
            inactive_m = inactive_res.scalar_one_or_none()
            if inactive_m and not inactive_m.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User membership in this tenant has been revoked or is inactive.",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to the requested tenant.",
            )
    else:
        target_membership = active_memberships[0]

    # 4. Set PostgreSQL session tenant context for Row-Level Security
    await set_session_tenant_context(session, target_membership.tenant_id)

    return AuthenticatedTenantContext(user=user, membership=target_membership)


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
async def get_data_status(
    auth_ctx: AuthenticatedTenantContext = Depends(get_authenticated_tenant_context),
    state: Any = Depends(get_app_state),
    session: AsyncSession = Depends(get_db_session),
) -> DataMetadata:
    """Check dataset source metadata scoped to authenticated tenant."""
    tenant_id = auth_ctx.tenant_id
    meta_cache = getattr(state, "tenant_metadata", {})
    cached_meta = meta_cache.get(tenant_id) or meta_cache.get(str(tenant_id))
    if cached_meta is not None:
        if isinstance(cached_meta, dict):
            return DataMetadata(**cached_meta)
        return cached_meta

    # Retrieve from active snapshot in database
    try:
        await set_session_tenant_context(session, tenant_id)
        stmt = select(SnapshotMetadata).where(
            SnapshotMetadata.tenant_id == tenant_id,
            SnapshotMetadata.is_active == True,
        )
        res = await session.execute(stmt)
        snapshot = res.scalar_one_or_none()
        if snapshot:
            meta_dict = {
                "data_source": snapshot.data_source,
                "data_status": snapshot.data_status,
                "last_updated_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
                "fallback_reason": None,
            }
            if meta_cache is not None:
                meta_cache[tenant_id] = meta_dict
            return DataMetadata(**meta_dict)
    except Exception as e:
        logger.warning("Could not fetch snapshot metadata for tenant %s: %s", tenant_id, e)

    return DataMetadata(
        data_source="unavailable",
        data_status="unavailable",
        last_updated_at=None,
        fallback_reason="No active snapshot found for this tenant.",
    )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Dashboard Metrics",
    description="Retrieves pre-computed, in-memory cached business intelligence metrics.",
)
async def get_cached_metrics(
    auth_ctx: AuthenticatedTenantContext = Depends(get_authenticated_tenant_context),
    state: Any = Depends(get_app_state),
    session: AsyncSession = Depends(get_db_session),
) -> MetricsResponse:
    """Return in-memory cached business dashboard metrics scoped to authenticated tenant without recalculating."""
    tenant_id = auth_ctx.tenant_id
    logger.info("Handling GET /metrics request for tenant %s (user %s).", tenant_id, auth_ctx.user_id)

    metrics_cache = getattr(state, "tenant_metrics_cache", {})
    meta_cache = getattr(state, "tenant_metadata", {})

    # Fast path: in-memory cache hit (support both UUID and str keys)
    cached_metrics = metrics_cache.get(tenant_id) or metrics_cache.get(str(tenant_id))
    if cached_metrics is not None:
        raw_meta = meta_cache.get(tenant_id) or meta_cache.get(str(tenant_id)) or getattr(state, "data_metadata", None)
        meta = DataMetadata(**raw_meta) if isinstance(raw_meta, dict) else raw_meta
        return MetricsResponse(dashboard_metrics=cached_metrics, data_metadata=meta)

    # Dynamic tenant lookup in database
    try:
        await set_session_tenant_context(session, tenant_id)
        stmt = select(SnapshotMetadata).where(
            SnapshotMetadata.tenant_id == tenant_id,
            SnapshotMetadata.is_active == True,
        )
        res = await session.execute(stmt)
        snapshot = res.scalar_one_or_none()
        if not snapshot or not snapshot.metrics_cache:
            fb_reason = getattr(state, "fallback_reason", None) or f"No active snapshot found for tenant {tenant_id}."
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"No usable dataset available: {fb_reason}",
            )

        meta = DataMetadata(
            data_source=snapshot.data_source,
            data_status=snapshot.data_status,
            last_updated_at=snapshot.created_at.isoformat() if snapshot.created_at else None,
            fallback_reason=None,
        )
        if metrics_cache is not None:
            metrics_cache[tenant_id] = snapshot.metrics_cache
        if meta_cache is not None:
            meta_cache[tenant_id] = meta.dict()

        return MetricsResponse(dashboard_metrics=snapshot.metrics_cache, data_metadata=meta)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error loading metrics for tenant %s: %s", tenant_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load metrics: {str(e)}",
        )


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask Business Intelligence Agent",
    description="Ask strategic business questions to the AI Business Intelligence Agent based on pre-computed metrics.",
)
async def ask_question(
    payload: AskRequest,
    auth_ctx: AuthenticatedTenantContext = Depends(get_authenticated_tenant_context),
    state: Any = Depends(get_app_state),
) -> AskResponse:
    """Ask strategic executive business question scoped to authenticated tenant."""
    tenant_id = auth_ctx.tenant_id
    logger.info("Handling POST /ask request for tenant %s with question: '%s'", tenant_id, payload.question)

    if getattr(state, "data_status", None) == "unavailable" or (
        getattr(state, "dashboard_metrics", None) is None
        and not getattr(state, "tenant_metrics_cache", {}).get(tenant_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No usable dataset could be loaded: Both Monday.com API and local Excel backup sources are unavailable.",
        )

    bi_agent = getattr(state, "tenant_bi_agents", {}).get(tenant_id) or getattr(state, "bi_agent", None)
    if bi_agent is None:
        logger.error("BIAgent not initialized (missing API key or startup failure).")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BI Agent service is unavailable. Please verify GROQ_API_KEY configuration.",
        )

    dfs_tuple = getattr(state, "tenant_dfs", {}).get(tenant_id)
    if dfs_tuple:
        deals_df, wo_df, quality_report = dfs_tuple
    else:
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
    auth_ctx: AuthenticatedTenantContext = Depends(get_authenticated_tenant_context),
    state: Any = Depends(get_app_state),
) -> LeadershipReportResponse:
    """Generate executive leadership report in Markdown scoped to authenticated tenant."""
    tenant_id = auth_ctx.tenant_id
    logger.info("Handling GET /leadership-report request for tenant %s.", tenant_id)

    if getattr(state, "data_status", None) == "unavailable" or (
        getattr(state, "dashboard_metrics", None) is None
        and not getattr(state, "tenant_metrics_cache", {}).get(tenant_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No usable dataset could be loaded: Both Monday.com API and local Excel backup sources are unavailable.",
        )

    bi_agent = getattr(state, "tenant_bi_agents", {}).get(tenant_id) or getattr(state, "bi_agent", None)
    if bi_agent is None:
        logger.error("BIAgent not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BI Agent service is unavailable. Please verify GROQ_API_KEY configuration.",
        )

    dfs_tuple = getattr(state, "tenant_dfs", {}).get(tenant_id)
    if dfs_tuple:
        deals_df, wo_df, quality_report = dfs_tuple
    else:
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
