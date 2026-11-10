"""
API Boundary and JSON Serialization Regression Tests.

Verifies:
1. Strict RFC 8259 JSON compliance across all API endpoints:
   Rejects non-standard tokens (NaN, Infinity, -Infinity).
2. Missing values serialize as JSON null or documented representations.
3. Actual HTTP endpoint responses (status 200, schema consistency) for:
   - /health
   - /ready
   - /data-status
   - /metrics
   - /ask
   - /leadership-report
4. Response schemas remain compatible with Pydantic response models.
"""

import json
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from api.routes import get_authenticated_tenant_context, AuthenticatedTenantContext
from db.models.tenant import User, TenantMembership
import uuid

def mock_auth_context():
    dummy_user = User(
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        email="test@skylarp.com",
        full_name="Test User",
        is_active=True,
    )
    dummy_membership = TenantMembership(
        membership_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        tenant_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        user_id=dummy_user.user_id,
        role="OWNER",
        is_active=True,
    )
    return AuthenticatedTenantContext(user=dummy_user, membership=dummy_membership)
from models.schemas import (
    AskResponse,
    DataMetadata,
    HealthResponse,
    LeadershipReportResponse,
    MetricsResponse,
    ReadyResponse,
)


def _assert_strict_rfc8259_json(raw_text: str) -> dict:
    """
    Parse JSON text strictly according to RFC 8259.
    Fails if JavaScript non-standard constants (NaN, Infinity, -Infinity) are present.
    """
    def _forbid_constant(token: str):
        raise AssertionError(f"Non-standard JSON token detected in response: {token}")

    # Explicit substring checks
    assert "NaN" not in raw_text, "Found 'NaN' in API response payload"
    assert "Infinity" not in raw_text, "Found 'Infinity' in API response payload"
    assert "-Infinity" not in raw_text, "Found '-Infinity' in API response payload"

    return json.loads(raw_text, parse_constant=_forbid_constant)


def test_core_endpoints_strict_json_serialization():
    """Verify /health, /ready, /data-status, and /metrics with lifespan-loaded data."""
    app.dependency_overrides[get_authenticated_tenant_context] = mock_auth_context
    try:
        with TestClient(app) as client:
            # 1. /health
            r_health = client.get("/health")
            assert r_health.status_code == 200
            health_data = _assert_strict_rfc8259_json(r_health.text)
            assert health_data["status"] == "healthy"
            HealthResponse(**health_data)

            # 2. /ready
            r_ready = client.get("/ready")
            assert r_ready.status_code == 200
            ready_data = _assert_strict_rfc8259_json(r_ready.text)
            assert ready_data["status"] == "ready"
            ReadyResponse(**ready_data)

            # 3. /data-status
            r_status = client.get("/data-status")
            assert r_status.status_code == 200
            status_data = _assert_strict_rfc8259_json(r_status.text)
            assert status_data["data_source"] in ("excel_fallback", "monday_api")
            assert status_data["data_status"] in ("fallback", "live")
            assert status_data["data_as_of"] is None  # Serializes as JSON null
            DataMetadata(**status_data)

            # 4. /metrics
            r_metrics = client.get("/metrics")
            assert r_metrics.status_code == 200
            metrics_data = _assert_strict_rfc8259_json(r_metrics.text)
            MetricsResponse(**metrics_data)

            dashboard = metrics_data["dashboard_metrics"]
            ps = dashboard["pipeline_summary"]
            vc = ps["value_coverage"]

            # Invariant check on API serialized payload
            assert vc["valid_numeric_count"] + vc["missing_value_count"] + vc["invalid_value_count"] == vc["total_records"]
            assert isinstance(ps["gross_historical_opportunity_value"], (int, float))
            assert isinstance(ps["active_pipeline_value"], (int, float))
            assert isinstance(ps["average_deal_value"], (int, float))
    finally:
        app.dependency_overrides.pop(get_authenticated_tenant_context, None)


def test_ai_endpoints_strict_json_with_mocked_agent():
    """Verify /ask and /leadership-report return strictly compliant JSON."""
    app.dependency_overrides[get_authenticated_tenant_context] = mock_auth_context
    try:
        with TestClient(app) as client:
            class MockBIAgent:
                def answer_question(self, *args, **kwargs):
                    return {
                        "answer": "Executive analysis verified with strict numeric integrity.",
                        "dashboard_metrics": client.app.state.dashboard_metrics,
                        "data_quality_notes": ["Note 1: Unmarked values confirmed as INR"],
                    }

                def generate_leadership_report(self, *args, **kwargs):
                    return {
                        "report": "# Executive Leadership Report\n\n- All KPIs reconciled.\n- Currency: INR"
                    }

            client.app.state.bi_agent = MockBIAgent()

            # POST /ask
            r_ask = client.post("/ask", json={"question": "What is our pipeline status?"})
            assert r_ask.status_code == 200
            ask_data = _assert_strict_rfc8259_json(r_ask.text)
            AskResponse(**ask_data)
            assert "Executive analysis verified" in ask_data["answer"]

            # GET /leadership-report
            r_report = client.get("/leadership-report")
            assert r_report.status_code == 200
            report_data = _assert_strict_rfc8259_json(r_report.text)
            LeadershipReportResponse(**report_data)
            assert "Executive Leadership Report" in report_data["report"]
    finally:
        app.dependency_overrides.pop(get_authenticated_tenant_context, None)

