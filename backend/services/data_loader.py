"""
Data Loader Module for Monday.com BI Application.
Provides reliable multi-source ingestion with automatic fallback from
Monday.com GraphQL v2 API to local Excel backup workbooks.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import Any, Tuple

import pandas as pd

from services.monday_service import MondayAPIError, MondayClient

logger = logging.getLogger(__name__)

# Recognized placeholder values for environment variables
PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "your_monday_api_key_here",
    "your_monday_api_token_here",
    "your_monday_board_id_here",
    "your_deals_board_id_here",
    "your_work_orders_board_id_here",
}

DEALS_EXCEL_FILENAME = "Deal funnel Data.xlsx"
WORK_ORDERS_EXCEL_FILENAME = "Work_Order_Tracker Data.xlsx"


class DataSourceError(Exception):
    """Base exception for data ingestion failures."""
    pass


class ExcelLoadError(DataSourceError):
    """Raised when local Excel backup loading fails."""
    pass


# Controlled public error codes / messages
MONDAY_API_UNAVAILABLE = "MONDAY_API_UNAVAILABLE: Monday.com API service was unreachable or returned an error."
EXCEL_BACKUP_UNAVAILABLE = "EXCEL_BACKUP_UNAVAILABLE: Historical Excel backup files could not be loaded."
DATA_SOURCES_UNAVAILABLE = "DATA_SOURCES_UNAVAILABLE: Both Monday.com API and local Excel backup sources are unavailable."
CREDENTIALS_NOT_CONFIGURED = "CREDENTIALS_NOT_CONFIGURED: Monday.com credentials are not configured; fallback activated."


def sanitize_error_message(msg: str) -> str:
    """
    Remove potentially sensitive tokens, keys, auth headers, and filesystem paths from error messages.
    """
    if not msg:
        return "Unknown error"

    sanitized = str(msg)
    # Redact potential bearer/auth tokens or hex keys (>=20 alphanumeric characters)
    sanitized = re.sub(r"([a-zA-Z0-9_-]{20,})", "[REDACTED]", sanitized)
    sanitized = re.sub(r"(Bearer\s+)[^\s]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"(Authorization['\":\s]+)[^\s,]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)

    # Redact Windows paths (e.g. C:\..., D:\..., or relative ..\...)
    sanitized = re.sub(r"[A-Za-z]:\\[^:\n\r\t]+?\\", "[PATH]\\\\", sanitized)
    # Redact Unix paths (/foo/bar/...)
    sanitized = re.sub(r"/(?:[a-zA-Z0-9._-]+/)+", "[PATH]/", sanitized)

    return sanitized.strip()


def is_valid_credential(val: str | None) -> bool:
    """Check if credential is non-empty and not a recognized placeholder."""
    if not val:
        return False
    return val.strip().lower() not in PLACEHOLDER_VALUES


def load_from_monday(
    api_key: str, deals_board_id: str, wo_board_id: str
) -> Tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Fetch and parse live board records from Monday.com GraphQL API.

    Raises:
        MondayAPIError: If API request fails or returns errors.
    """
    logger.info("Connecting to Monday.com API to fetch Deals and Work Orders...")
    try:
        client = MondayClient(api_key=api_key)
        raw_deals_items = client.fetch_board_items(deals_board_id)
        raw_deals = client.parse_items_to_dicts(raw_deals_items)

        raw_wo_items = client.fetch_board_items(wo_board_id)
        raw_work_orders = client.parse_items_to_dicts(raw_wo_items)

        if not isinstance(raw_deals, list) or not isinstance(raw_work_orders, list):
            raise MondayAPIError("Monday.com API returned malformed item lists.")

        logger.info(
            "Successfully fetched live data from Monday.com: %d deals, %d work orders.",
            len(raw_deals),
            len(raw_work_orders),
        )
        return raw_deals, raw_work_orders

    except Exception as e:
        clean_err = sanitize_error_message(str(e))
        logger.warning("Monday.com API fetch failed: %s", clean_err)
        if isinstance(e, MondayAPIError):
            raise
        raise MondayAPIError(f"Monday.com API failure: {clean_err}") from e


def load_from_excel(
    root_dir: Path,
    deals_filename: str = DEALS_EXCEL_FILENAME,
    wo_filename: str = WORK_ORDERS_EXCEL_FILENAME,
) -> Tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """
    Load raw records from local Excel backup workbooks.

    Returns:
        Tuple of (raw_deals, raw_work_orders, source_modified_at_dict)

    Raises:
        ExcelLoadError: If files do not exist or cannot be parsed.
    """
    deal_file = root_dir / deals_filename
    wo_file = root_dir / wo_filename

    if not deal_file.exists():
        raise ExcelLoadError(f"Deals backup Excel file not found: {deal_file.name}")
    if not wo_file.exists():
        raise ExcelLoadError(f"Work Orders backup Excel file not found: {wo_file.name}")

    try:
        deals_mtime = datetime.fromtimestamp(deal_file.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        deals_mtime = None

    try:
        wo_mtime = datetime.fromtimestamp(wo_file.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        wo_mtime = None

    source_modified_at = {
        "deals_file": deal_file.name,
        "deals_modified_at": deals_mtime,
        "work_orders_file": wo_file.name,
        "work_orders_modified_at": wo_mtime,
    }

    try:
        logger.info("Loading Deals from local Excel: %s", deal_file.name)
        deals_df = pd.read_excel(deal_file)
        raw_deals = deals_df.to_dict(orient="records")
    except Exception as e:
        raise ExcelLoadError(f"Failed to read Deals Excel file '{deal_file.name}': {e}") from e

    try:
        logger.info("Loading Work Orders from local Excel: %s", wo_file.name)
        # Work orders dataset column header starts on row index 1
        wo_df = pd.read_excel(wo_file, header=1)
        raw_work_orders = wo_df.to_dict(orient="records")
    except Exception as e:
        raise ExcelLoadError(f"Failed to read Work Orders Excel file '{wo_file.name}': {e}") from e

    if not raw_deals and not raw_work_orders:
        raise ExcelLoadError("Excel backup files contained no records.")

    logger.info(
        "Successfully loaded Excel backup: %d deals, %d work orders.",
        len(raw_deals),
        len(raw_work_orders),
    )
    return raw_deals, raw_work_orders, source_modified_at


def load_dataset(
    api_key: str | None = None,
    deals_board_id: str | None = None,
    wo_board_id: str | None = None,
    root_dir: Path | None = None,
) -> Tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """
    Source-selection orchestrator implementing reliable Monday.com API failure fallback to Excel.

    Evaluation steps:
    1. If valid Monday.com credentials exist, attempt to fetch live data.
    2. If live API fetch succeeds and returned data is valid, use live data.
    3. If API request fails (HTTP 500, timeout, connection, GraphQL error), attempt Excel fallback.
    4. If credentials missing or placeholders, load Excel directly.
    5. If Excel loading fails (missing/corrupted file), return explicit unavailable state.
    6. If both sources fail, return explicit unavailable state.

    Returns:
        Tuple of (raw_deals, raw_work_orders, data_metadata)
    """
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent.parent

    has_creds = (
        is_valid_credential(api_key)
        and is_valid_credential(deals_board_id)
        and is_valid_credential(wo_board_id)
    )

    fallback_reason: str | None = None
    api_failure_occurred = False
    now_utc = datetime.now(timezone.utc).isoformat()

    # 1. Attempt live Monday.com API if credentials are present
    if has_creds:
        logger.info("--- STARTUP ATTEMPT: LIVE MONDAY.COM API ---")
        try:
            raw_deals, raw_work_orders = load_from_monday(
                api_key=api_key,  # type: ignore[arg-type]
                deals_board_id=deals_board_id,  # type: ignore[arg-type]
                wo_board_id=wo_board_id,  # type: ignore[arg-type]
            )
            metadata = {
                "data_source": "monday_api",
                "data_status": "live",
                "loaded_at": now_utc,
                "source_modified_at": None,
                "data_as_of": None,
                "last_updated_at": now_utc,
                "fallback_reason": None,
            }
            return raw_deals, raw_work_orders, metadata
        except Exception as e:
            api_failure_occurred = True
            raw_err = sanitize_error_message(str(e))
            logger.warning(
                "Live API ingestion failed (%s). Activating local Excel fallback...",
                raw_err,
            )
            fallback_reason = MONDAY_API_UNAVAILABLE
    else:
        logger.info("--- STARTUP MODE: DIRECT EXCEL BACKUP (Credentials not configured) ---")
        fallback_reason = CREDENTIALS_NOT_CONFIGURED

    # 2. Attempt Excel fallback
    logger.info("Attempting to load local Excel backup from directory: %s", root_dir)
    try:
        raw_deals, raw_work_orders, source_mtime = load_from_excel(root_dir=root_dir)
        metadata = {
            "data_source": "excel_fallback",
            "data_status": "fallback",
            "loaded_at": now_utc,
            "source_modified_at": source_mtime,
            "data_as_of": None,
            "last_updated_at": now_utc,
            "fallback_reason": fallback_reason,
        }
        return raw_deals, raw_work_orders, metadata
    except Exception as e:
        excel_err = sanitize_error_message(str(e))
        logger.error("Excel backup loading failed: %s", excel_err)

        metadata = {
            "data_source": "unavailable",
            "data_status": "unavailable",
            "loaded_at": None,
            "source_modified_at": None,
            "data_as_of": None,
            "last_updated_at": None,
            "fallback_reason": DATA_SOURCES_UNAVAILABLE,
        }
        return [], [], metadata

