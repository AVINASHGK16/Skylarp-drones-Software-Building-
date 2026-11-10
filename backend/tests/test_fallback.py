"""
Unit and Integration Tests for Monday.com API Failure Fallback to Excel.

Scenarios:
1. Successful Monday.com API fetch.
2. Monday.com HTTP 500 followed by successful Excel fallback.
3. Monday.com timeout followed by successful Excel fallback.
4. Monday.com GraphQL error followed by successful Excel fallback.
5. Missing or placeholder credentials causing direct Excel loading.
6. Missing Excel file after API failure.
7. Corrupted Excel file after API failure.
8. Both sources failing: Natural lifespan initialization and endpoint HTTP 503 degradation.
9. Correct source/status metadata & timestamp semantics across all modes.
10. Board validation: Empty boards list raises MondayAPIError and triggers Excel fallback.
11. Board validation: Board exists with empty items is valid live dataset (not error).
12. Board validation: Malformed boards/items response structure raises controlled MondayAPIError.
13. Security: Redaction of filesystem paths, auth tokens, and GraphQL errors.
14. Health check separation: /health (liveness 200) vs /ready (readiness 200 vs 503).
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient

import uuid
from api.routes import get_authenticated_tenant_context, AuthenticatedTenantContext
from db.models.tenant import User, TenantMembership


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


# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app, initialize_app_data
from services.data_loader import (
    load_dataset,
    load_from_excel,
    load_from_monday,
    is_valid_credential,
    sanitize_error_message,
    MondayAPIError,
    ExcelLoadError,
    MONDAY_API_UNAVAILABLE,
    EXCEL_BACKUP_UNAVAILABLE,
    DATA_SOURCES_UNAVAILABLE,
)
from services.monday_service import MondayClient


# -----------------------------------------------------------------------------
# Fixture Helpers
# -----------------------------------------------------------------------------

def create_mock_excel_files(target_dir: Path):
    """Create valid minimal Deals and Work Orders Excel workbooks in target_dir."""
    deals_data = {
        "Masked Deal ID": ["D-001"],
        "Masked Deal name": ["Alpha Deal"],
        "Masked Deal value": [150000],
        "Deal Status": ["Won"],
        "Deal Stage": ["Closed Won"],
        "Sector/service": ["Mining"],
        "Created Date": ["2026-01-15"],
    }
    deals_df = pd.DataFrame(deals_data)
    deals_path = target_dir / "Deal funnel Data.xlsx"
    deals_df.to_excel(deals_path, index=False)

    # Work orders table has headers on row index 1
    wo_headers = ["Masked WO ID", "Customer Name Code", "Execution Status", "Amount in Rupees (Excl of GST) (Masked)", "Billed Value in Rupees (Excl of GST.) (Masked)", "Start Date", "End Date"]
    wo_row = ["WO-001", "CUST_001", "Completed", 100000, 100000, "2026-02-01", "2026-02-15"]
    wo_df = pd.DataFrame([wo_row], columns=wo_headers)
    wo_path = target_dir / "Work_Order_Tracker Data.xlsx"
    # Write empty row at index 0, headers on row 1
    with pd.ExcelWriter(wo_path) as writer:
        pd.DataFrame([[""] * len(wo_headers)]).to_excel(writer, index=False, header=False, startrow=0)
        wo_df.to_excel(writer, index=False, header=True, startrow=1)


MOCK_DEALS_ITEMS = [
    {
        "id": "deal_001",
        "name": "Live Alpha Deal",
        "column_values": [
            {"id": "deal_value", "text": "150000", "column": {"title": "Masked Deal value"}},
            {"id": "status", "text": "Won", "column": {"title": "Deal Status"}},
            {"id": "stage", "text": "Closed Won", "column": {"title": "Deal Stage"}},
            {"id": "sector", "text": "Mining", "column": {"title": "Sector/service"}},
        ],
    }
]

MOCK_WO_ITEMS = [
    {
        "id": "wo_001",
        "name": "Live WO Alpha",
        "column_values": [
            {"id": "customer", "text": "CUST_LIVE", "column": {"title": "Customer Name Code"}},
            {"id": "status", "text": "Completed", "column": {"title": "Execution Status"}},
            {"id": "amount", "text": "100000", "column": {"title": "Amount in Rupees (Excl of GST) (Masked)"}},
            {"id": "billed", "text": "100000", "column": {"title": "Billed Value in Rupees (Excl of GST.) (Masked)"}},
        ],
    }
]


# =============================================================================
# SCENARIO 1: Successful Monday.com API Fetch
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_1_successful_monday_api_fetch(mock_fetch):
    """Scenario 1: Valid credentials + successful Monday API response uses live data."""
    mock_fetch.side_effect = lambda board_id: MOCK_DEALS_ITEMS if board_id == "deals_1" else MOCK_WO_ITEMS

    raw_deals, raw_wo, meta = load_dataset(
        api_key="valid_token_xyz_12345",
        deals_board_id="deals_1",
        wo_board_id="wo_1",
        root_dir=ROOT_DIR,
    )

    assert len(raw_deals) == 1
    assert raw_deals[0]["name"] == "Live Alpha Deal"
    assert raw_deals[0]["Masked Deal value"] == "150000"

    assert len(raw_wo) == 1
    assert raw_wo[0]["name"] == "Live WO Alpha"

    assert meta["data_source"] == "monday_api"
    assert meta["data_status"] == "live"
    assert meta["fallback_reason"] is None
    assert meta["loaded_at"] is not None
    assert meta["last_updated_at"] is not None
    assert meta["data_as_of"] is None
    assert meta["source_modified_at"] is None


# =============================================================================
# SCENARIO 2: Monday.com HTTP 500 Followed by Successful Excel Fallback
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_2_monday_http_500_excel_fallback(mock_fetch):
    """Scenario 2: Monday.com HTTP 500 error triggers automatic Excel fallback."""
    mock_fetch.side_effect = requests.exceptions.HTTPError("500 Server Error: Internal Server Error")

    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        create_mock_excel_files(td)

        raw_deals, raw_wo, meta = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="deals_1",
            wo_board_id="wo_1",
            root_dir=td,
        )

        assert len(raw_deals) == 1
        assert len(raw_wo) == 1
        assert meta["data_source"] == "excel_fallback"
        assert meta["data_status"] == "fallback"
        assert meta["fallback_reason"] == MONDAY_API_UNAVAILABLE
        assert meta["loaded_at"] is not None
        assert meta["source_modified_at"] is not None
        assert "deals_modified_at" in meta["source_modified_at"]


# =============================================================================
# SCENARIO 3: Monday.com Timeout Followed by Successful Excel Fallback
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_3_monday_timeout_excel_fallback(mock_fetch):
    """Scenario 3: Monday.com API timeout triggers automatic Excel fallback."""
    mock_fetch.side_effect = requests.exceptions.Timeout("Connection timed out after 30 seconds")

    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        create_mock_excel_files(td)

        raw_deals, raw_wo, meta = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="deals_1",
            wo_board_id="wo_1",
            root_dir=td,
        )

        assert len(raw_deals) == 1
        assert len(raw_wo) == 1
        assert meta["data_source"] == "excel_fallback"
        assert meta["data_status"] == "fallback"
        assert meta["fallback_reason"] == MONDAY_API_UNAVAILABLE


# =============================================================================
# SCENARIO 4: Monday.com GraphQL Error Followed by Successful Excel Fallback
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_4_monday_graphql_error_excel_fallback(mock_fetch):
    """Scenario 4: Monday.com GraphQL error payload triggers automatic Excel fallback."""
    mock_fetch.side_effect = MondayAPIError(
        "Monday.com API GraphQL errors: [{'message': 'Complexity budget exhausted'}]"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        create_mock_excel_files(td)

        raw_deals, raw_wo, meta = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="deals_1",
            wo_board_id="wo_1",
            root_dir=td,
        )

        assert len(raw_deals) == 1
        assert len(raw_wo) == 1
        assert meta["data_source"] == "excel_fallback"
        assert meta["data_status"] == "fallback"
        assert meta["fallback_reason"] == MONDAY_API_UNAVAILABLE


# =============================================================================
# SCENARIO 5: Missing or Placeholder Credentials Causing Direct Excel Loading
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_5_missing_credentials_direct_excel(mock_fetch):
    """Scenario 5: Missing or placeholder API keys skip live attempt and load Excel directly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        create_mock_excel_files(td)

        # None credentials
        raw_deals, raw_wo, meta_none = load_dataset(
            api_key=None,
            deals_board_id=None,
            wo_board_id=None,
            root_dir=td,
        )
        assert len(raw_deals) == 1
        assert meta_none["data_source"] == "excel_fallback"
        assert meta_none["data_status"] == "fallback"
        mock_fetch.assert_not_called()

        # Placeholder string
        raw_deals_p, _, meta_placeholder = load_dataset(
            api_key="your_monday_api_key_here",
            deals_board_id="your_deals_board_id_here",
            wo_board_id="your_work_orders_board_id_here",
            root_dir=td,
        )
        assert len(raw_deals_p) == 1
        assert meta_placeholder["data_source"] == "excel_fallback"
        mock_fetch.assert_not_called()


# =============================================================================
# SCENARIO 6: Missing Excel File After API Failure
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_6_missing_excel_file_after_api_failure(mock_fetch):
    """Scenario 6: API failure followed by missing Excel file results in unavailable state."""
    mock_fetch.side_effect = requests.exceptions.ConnectionError("Network unreachable")

    with tempfile.TemporaryDirectory() as empty_temp_dir:
        raw_deals, raw_wo, meta = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="deals_1",
            wo_board_id="wo_1",
            root_dir=Path(empty_temp_dir),
        )

        assert raw_deals == []
        assert raw_wo == []
        assert meta["data_source"] == "unavailable"
        assert meta["data_status"] == "unavailable"
        assert meta["loaded_at"] is None
        assert meta["fallback_reason"] == DATA_SOURCES_UNAVAILABLE


# =============================================================================
# SCENARIO 7: Corrupted Excel File After API Failure
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_7_corrupted_excel_file_after_api_failure(mock_fetch):
    """Scenario 7: API failure followed by corrupt Excel files results in unavailable state."""
    mock_fetch.side_effect = MondayAPIError("API down")

    with tempfile.TemporaryDirectory() as corrupt_temp_dir:
        p = Path(corrupt_temp_dir)
        (p / "Deal funnel Data.xlsx").write_bytes(b"CORRUPTED_NOT_A_VALID_ZIP_OR_EXCEL")
        (p / "Work_Order_Tracker Data.xlsx").write_bytes(b"CORRUPTED_NOT_A_VALID_ZIP_OR_EXCEL")

        raw_deals, raw_wo, meta = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="deals_1",
            wo_board_id="wo_1",
            root_dir=p,
        )

        assert raw_deals == []
        assert raw_wo == []
        assert meta["data_source"] == "unavailable"
        assert meta["data_status"] == "unavailable"
        assert meta["fallback_reason"] == DATA_SOURCES_UNAVAILABLE


# =============================================================================
# SCENARIO 8: Both Sources Failing — Natural Startup Lifespan & 503 Degradation
# =============================================================================

@patch("main.load_dataset")
def test_8_both_sources_failing_natural_startup_and_503(mock_load):
    """Scenario 8: When load_dataset fails naturally during lifespan, endpoints return HTTP 503."""
    mock_load.return_value = (
        [],
        [],
        {
            "data_source": "unavailable",
            "data_status": "unavailable",
            "loaded_at": None,
            "source_modified_at": None,
            "data_as_of": None,
            "last_updated_at": None,
            "fallback_reason": DATA_SOURCES_UNAVAILABLE,
        },
    )

    app.dependency_overrides[get_authenticated_tenant_context] = mock_auth_context
    try:
        with TestClient(app) as client:
            # Verify app initialized into unavailable state
            assert app.state.data_status == "unavailable"
            assert app.state.data_source == "unavailable"
            assert app.state.dashboard_metrics is None

            # 1. GET /metrics must reject with HTTP 503
            res_metrics = client.get("/metrics")
            assert res_metrics.status_code == 503
            metrics_body = res_metrics.json()
            assert "No usable dataset available" in metrics_body["detail"]
            assert "DATA_SOURCES_UNAVAILABLE" in metrics_body["detail"]

            # 2. POST /ask must reject with HTTP 503
            res_ask = client.post("/ask", json={"question": "What is our revenue?"})
            assert res_ask.status_code == 503
            ask_body = res_ask.json()
            assert "No usable dataset could be loaded" in ask_body["detail"]

            # 3. GET /leadership-report must reject with HTTP 503
            res_report = client.get("/leadership-report")
            assert res_report.status_code == 503
            report_body = res_report.json()
            assert "No usable dataset could be loaded" in report_body["detail"]

            # 4. GET /data-status reflects exact unavailable status (HTTP 200)
            res_status = client.get("/data-status")
            assert res_status.status_code == 200
            status_body = res_status.json()
            assert status_body["data_status"] == "unavailable"
            assert status_body["data_source"] == "unavailable"
            assert status_body["loaded_at"] is None
            assert status_body["fallback_reason"] == DATA_SOURCES_UNAVAILABLE

            # 5. GET /ready returns HTTP 503
            res_ready = client.get("/ready")
            assert res_ready.status_code == 503
            ready_body = res_ready.json()
            assert ready_body["status"] == "not_ready"
            assert ready_body["data_status"] == "unavailable"

            # 6. GET /health remains 200 OK (liveness)
            res_health = client.get("/health")
            assert res_health.status_code == 200
            assert res_health.json()["status"] == "healthy"
    finally:
        app.dependency_overrides.pop(get_authenticated_tenant_context, None)


# =============================================================================
# SCENARIO 9: Metadata & Timestamp Semantics
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_9_metadata_timestamp_semantics(mock_fetch):
    """Scenario 9: loaded_at is populated, data_as_of is null, source_modified_at is tracked for Excel."""
    mock_fetch.side_effect = lambda board_id: MOCK_DEALS_ITEMS if board_id == "deals_1" else MOCK_WO_ITEMS

    # Live API metadata
    _, _, meta_live = load_dataset(
        api_key="valid_token_xyz_12345",
        deals_board_id="deals_1",
        wo_board_id="wo_1",
        root_dir=ROOT_DIR,
    )
    assert meta_live["data_source"] == "monday_api"
    assert meta_live["data_status"] == "live"
    assert meta_live["loaded_at"] is not None
    assert meta_live["source_modified_at"] is None
    assert meta_live["data_as_of"] is None

    # Excel Fallback metadata
    mock_fetch.side_effect = requests.exceptions.HTTPError("500 Server Error")
    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        create_mock_excel_files(td)

        _, _, meta_fb = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="deals_1",
            wo_board_id="wo_1",
            root_dir=td,
        )
        assert meta_fb["data_source"] == "excel_fallback"
        assert meta_fb["data_status"] == "fallback"
        assert meta_fb["loaded_at"] is not None
        assert meta_fb["data_as_of"] is None
        assert isinstance(meta_fb["source_modified_at"], dict)
        assert meta_fb["source_modified_at"]["deals_file"] == "Deal funnel Data.xlsx"
        assert meta_fb["source_modified_at"]["deals_modified_at"] is not None


# =============================================================================
# SCENARIO 10: Monday.com Board Validation — Inaccessible/Missing Board triggers Fallback
# =============================================================================

@patch.object(MondayClient, "_execute_query")
def test_10_missing_inaccessible_board_triggers_fallback(mock_query):
    """Scenario 10: Empty boards array from Monday.com raises MondayAPIError and triggers fallback."""
    # Monday returns 200 with empty boards array when board ID is invalid or token lacks permissions
    mock_query.return_value = {
        "data": {
            "boards": []
        }
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        create_mock_excel_files(td)

        raw_deals, raw_wo, meta = load_dataset(
            api_key="valid_token_xyz_12345",
            deals_board_id="nonexistent_board_999",
            wo_board_id="wo_1",
            root_dir=td,
        )

        assert len(raw_deals) == 1
        assert meta["data_source"] == "excel_fallback"
        assert meta["data_status"] == "fallback"
        assert meta["fallback_reason"] == MONDAY_API_UNAVAILABLE


# =============================================================================
# SCENARIO 11: Monday.com Board Validation — Existing Board with 0 Items is Valid Live Dataset
# =============================================================================

@patch.object(MondayClient, "_execute_query")
def test_11_existing_board_with_zero_items_accepted_as_live(mock_query):
    """Scenario 11: Valid board with empty items array is treated as legitimate empty live dataset."""
    mock_query.return_value = {
        "data": {
            "boards": [
                {
                    "items_page": {
                        "cursor": None,
                        "items": []
                    }
                }
            ]
        }
    }

    client = MondayClient(api_key="valid_token_xyz_12345")
    items = client.fetch_board_items("board_with_no_deals")
    assert items == []

    raw_deals, raw_wo, meta = load_dataset(
        api_key="valid_token_xyz_12345",
        deals_board_id="board_empty_deals",
        wo_board_id="board_empty_wo",
        root_dir=ROOT_DIR,
    )
    assert raw_deals == []
    assert raw_wo == []
    assert meta["data_source"] == "monday_api"
    assert meta["data_status"] == "live"
    assert meta["fallback_reason"] is None


# =============================================================================
# SCENARIO 12: Monday.com Board Validation — Malformed Responses Structure
# =============================================================================

@patch.object(MondayClient, "_execute_query")
def test_12_malformed_response_structure_raises_error(mock_query):
    """Scenario 12: Missing 'boards' or 'items_page' or malformed types raise controlled MondayAPIError."""
    client = MondayClient(api_key="valid_token_xyz_12345")

    # 1. Missing data field
    mock_query.return_value = {"other_field": 123}
    with pytest.raises(MondayAPIError, match="missing 'data' field"):
        client.fetch_board_items("123")

    # 2. 'boards' is not a list
    mock_query.return_value = {"data": {"boards": "not-a-list"}}
    with pytest.raises(MondayAPIError, match="'boards' field is not a list"):
        client.fetch_board_items("123")

    # 3. Missing items_page
    mock_query.return_value = {"data": {"boards": [{"not_items_page": {}}]}}
    with pytest.raises(MondayAPIError, match="missing or invalid 'items_page'"):
        client.fetch_board_items("123")


# =============================================================================
# SCENARIO 13: Security & Sanitization
# =============================================================================

def test_13_security_sanitization_paths_tokens_and_headers():
    """Scenario 13: Windows/Unix paths, long tokens, and auth headers are stripped."""
    # Test path redaction
    win_err = r"Failed to open D:\Captures\Skylarp drones\Skylarp-drones-Software-Building-\backend\secret\config.json"
    sanitized_win = sanitize_error_message(win_err)
    assert r"D:\Captures" not in sanitized_win
    assert "[PATH]\\" in sanitized_win

    unix_err = "Cannot access /home/user/backend/secret/config.json"
    sanitized_unix = sanitize_error_message(unix_err)
    assert "/home/user" not in sanitized_unix
    assert "[PATH]/" in sanitized_unix

    # Test token redaction
    token_err = "Auth failed for token abcdef1234567890abcdef123456"
    sanitized_token = sanitize_error_message(token_err)
    assert "abcdef1234567890abcdef123456" not in sanitized_token
    assert "[REDACTED]" in sanitized_token


# =============================================================================
# SCENARIO 14: Health & Readiness Endpoint Separation
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_14_health_liveness_vs_readiness(mock_fetch):
    """Scenario 14: /health is always 200, /ready reflects business dataset status."""
    mock_fetch.side_effect = lambda board_id: MOCK_DEALS_ITEMS if board_id == "deals_1" else MOCK_WO_ITEMS

    with TestClient(app) as client:
        # Liveness probe
        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "healthy"}

        # Readiness probe
        res_ready = client.get("/ready")
        assert res_ready.status_code == 200
        ready_data = res_ready.json()
        assert ready_data["status"] == "ready"
        assert ready_data["data_status"] in ["live", "fallback"]

        # Readiness alias
        res_ready_alias = client.get("/health/ready")
        assert res_ready_alias.status_code == 200
        assert res_ready_alias.json()["status"] == "ready"


# =============================================================================
# SCENARIO 15: Exact JSON Response Shape for /data-status
# =============================================================================

@patch.object(MondayClient, "fetch_board_items")
def test_15_exact_data_status_json_schema(mock_fetch):
    """Scenario 15: Assert the exact JSON key structure returned by /data-status across modes."""
    # 1. Live mode JSON schema
    mock_fetch.side_effect = lambda board_id: MOCK_DEALS_ITEMS if board_id == "deals_1" else MOCK_WO_ITEMS
    app.dependency_overrides[get_authenticated_tenant_context] = mock_auth_context
    try:
        with TestClient(app) as client:
            # Re-initialize app to live state
            with patch.dict(os.environ, {
                "MONDAY_API_KEY": "valid_key_123456",
                "DEALS_BOARD_ID": "deals_1",
                "WORK_ORDERS_BOARD_ID": "wo_1",
            }):
                initialize_app_data(app)

            res_live = client.get("/data-status")
            assert res_live.status_code == 200
            live_json = res_live.json()
            assert set(live_json.keys()) == {
                "data_source",
                "data_status",
                "loaded_at",
                "source_modified_at",
                "data_as_of",
                "last_updated_at",
                "fallback_reason",
            }
            assert live_json["data_source"] == "monday_api"
            assert live_json["data_status"] == "live"
            assert live_json["source_modified_at"] is None
            assert live_json["data_as_of"] is None
            assert live_json["fallback_reason"] is None
            assert isinstance(live_json["loaded_at"], str)
            assert live_json["last_updated_at"] == live_json["loaded_at"]

            # 2. Fallback mode JSON schema
            mock_fetch.side_effect = requests.exceptions.HTTPError("500 Server Error")
            with patch.dict(os.environ, {
                "MONDAY_API_KEY": "valid_key_123456",
                "DEALS_BOARD_ID": "deals_1",
                "WORK_ORDERS_BOARD_ID": "wo_1",
            }):
                initialize_app_data(app)

            res_fb = client.get("/data-status")
            assert res_fb.status_code == 200
            fb_json = res_fb.json()
            assert set(fb_json.keys()) == {
                "data_source",
                "data_status",
                "loaded_at",
                "source_modified_at",
                "data_as_of",
                "last_updated_at",
                "fallback_reason",
            }
            assert fb_json["data_source"] == "excel_fallback"
            assert fb_json["data_status"] == "fallback"
            assert fb_json["data_as_of"] is None
            assert set(fb_json["source_modified_at"].keys()) == {
                "deals_file",
                "deals_modified_at",
                "work_orders_file",
                "work_orders_modified_at",
            }
    finally:
        app.dependency_overrides.pop(get_authenticated_tenant_context, None)
        assert fb_json["source_modified_at"]["deals_file"] == "Deal funnel Data.xlsx"
        assert fb_json["source_modified_at"]["work_orders_file"] == "Work_Order_Tracker Data.xlsx"
        assert isinstance(fb_json["source_modified_at"]["deals_modified_at"], str)
        assert isinstance(fb_json["source_modified_at"]["work_orders_modified_at"], str)
