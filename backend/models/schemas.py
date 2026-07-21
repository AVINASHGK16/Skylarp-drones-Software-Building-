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
        example="What are our top revenue-generating sectors and biggest risks?",
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


class HealthResponse(BaseModel):
    """API Health Check response."""

    status: str = Field(..., description="Health status of the API.", example="healthy")


class MetricsResponse(BaseModel):
    """Response payload containing cached business dashboard metrics."""

    dashboard_metrics: dict[str, Any] = Field(
        ..., description="Comprehensive business metrics dictionary."
    )


class RootResponse(BaseModel):
    """Response payload for root API endpoint."""

    message: str = Field(..., example="Business Intelligence Agent API")
