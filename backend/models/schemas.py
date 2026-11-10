"""
Pydantic Schemas for Business Intelligence Agent API.
Defines request and response data models with type safety and validation.
"""

from typing import Any
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request payload for asking strategic questions to the BI Agent."""

    question: str = Field(
        ...,
        description="The executive or strategic business question to ask.",
        json_schema_extra={"example": "What are our top revenue-generating sectors and biggest risks?"},
    )


class AskResponse(BaseModel):
    """Response payload returned from BI Agent Q&A."""

    answer: str = Field(
        ..., description="The AI Business Intelligence Agent's analysis and answer."
    )
    dashboard_metrics: dict[str, Any] = Field(
        ..., description="Pre-computed business metrics used for the analysis."
    )
    data_quality_notes: list[str] = Field(
        default_factory=list,
        description="Data quality caveats relevant to the underlying data.",
    )


class LeadershipReportResponse(BaseModel):
    """Response payload for generated executive leadership report."""

    report: str = Field(
        ..., description="Full executive report formatted in Markdown."
    )
    generated_at: str = Field(
        ..., description="ISO timestamp of when the report was generated."
    )


class ExcelSourceMetadata(BaseModel):
    """File-level modification metadata for Excel backup workbooks."""

    deals_file: str = Field(
        ...,
        description="Filename of the Deals backup workbook.",
        json_schema_extra={"example": "Deal funnel Data.xlsx"},
    )
    deals_modified_at: str | None = Field(
        default=None,
        description="ISO 8601 UTC filesystem modification timestamp of Deals file.",
        json_schema_extra={"example": "2026-07-21T10:00:00Z"},
    )
    work_orders_file: str = Field(
        ...,
        description="Filename of the Work Orders backup workbook.",
        json_schema_extra={"example": "Work_Order_Tracker Data.xlsx"},
    )
    work_orders_modified_at: str | None = Field(
        default=None,
        description="ISO 8601 UTC filesystem modification timestamp of Work Orders file.",
        json_schema_extra={"example": "2026-07-21T10:05:00Z"},
    )


class DataMetadata(BaseModel):
    """Metadata describing data source, status, and freshness."""

    data_source: str = Field(
        ...,
        description="Origin of loaded data: 'monday_api', 'excel_fallback', or 'unavailable'",
        json_schema_extra={"example": "monday_api"},
    )
    data_status: str = Field(
        ...,
        description="Status of dataset: 'live', 'fallback', or 'unavailable'",
        json_schema_extra={"example": "live"},
    )
    loaded_at: str | None = Field(
        default=None,
        description="ISO 8601 UTC timestamp of when backend loaded the data into memory",
        json_schema_extra={"example": "2026-11-08T17:00:00Z"},
    )
    source_modified_at: ExcelSourceMetadata | None = Field(
        default=None,
        description="Source file modification timestamps when loaded from Excel; null for live API",
    )
    data_as_of: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of source record validity; null if unestablished",
        json_schema_extra={"example": None},
    )
    last_updated_at: str | None = Field(
        default=None,
        description="[DEPRECATED] Alias for loaded_at maintained for frontend compatibility; do not use for data freshness",
        json_schema_extra={"example": "2026-11-08T17:00:00Z"},
    )
    fallback_reason: str | None = Field(
        default=None,
        description="Controlled explanation or error code when fallback is active or data is unavailable",
        json_schema_extra={"example": "MONDAY_API_UNAVAILABLE"},
    )


class HealthResponse(BaseModel):
    """API Health Check (liveness) response."""

    status: str = Field(
        ...,
        description="Liveness status of the API service process.",
        json_schema_extra={"example": "healthy"},
    )


class ReadyResponse(BaseModel):
    """API Readiness Check response indicating business data availability."""

    status: str = Field(
        ...,
        description="Readiness status: 'ready' when data is usable, 'not_ready' when unavailable.",
        json_schema_extra={"example": "ready"},
    )
    data_source: str = Field(
        ...,
        description="Active data source: 'monday_api', 'excel_fallback', or 'unavailable'.",
        json_schema_extra={"example": "live"},
    )
    data_status: str = Field(
        ...,
        description="Active dataset status: 'live', 'fallback', or 'unavailable'.",
        json_schema_extra={"example": "live"},
    )
    loaded_at: str | None = Field(
        default=None,
        description="ISO 8601 UTC timestamp of data loading.",
        json_schema_extra={"example": "2026-11-08T17:00:00Z"},
    )
    fallback_reason: str | None = Field(
        default=None,
        description="Controlled explanation if operating in degraded fallback mode.",
        json_schema_extra={"example": None},
    )


class MetricsResponse(BaseModel):
    """Response payload containing cached business dashboard metrics."""

    dashboard_metrics: dict[str, Any] = Field(
        ..., description="Comprehensive business metrics dictionary."
    )
    data_metadata: DataMetadata | None = Field(
        default=None, description="Metadata describing dataset source and freshness."
    )


class RootResponse(BaseModel):
    """Response payload for root API endpoint."""

    message: str = Field(..., json_schema_extra={"example": "Business Intelligence Agent API"})
