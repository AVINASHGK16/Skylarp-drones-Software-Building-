"""
Module for cleaning, normalizing, and validating Monday.com board data.
This module processes raw dictionary items fetched from Monday.com API into
clean, standardized Pandas DataFrames suitable for analytics pipelines.
"""

import copy
import logging
import re
from typing import Any

import pandas as pd

# Configure module logger
logger = logging.getLogger(__name__)

# Canonical Column Definitions
DEALS_CANONICAL_COLUMNS = [
    "id",
    "name",
    "Masked Deal value",
    "Close Date (A)",
    "Tentative Close Date",
    "Created Date",
    "Sector/service",
    "Deal Status",
    "Closure Probability",
    "Deal Stage",
]

WORK_ORDERS_CANONICAL_COLUMNS = [
    "id",
    "name",
    "Deal name masked",
    "Customer Name Code",
    "Execution Status",
    "Sector",
    "Type of Work",
    "Amount in Rupees (Excl of GST) (Masked)",
    "Billed Value in Rupees (Excl of GST.) (Masked)",
    "Probable Start Date",
    "Probable End Date",
    "Data Delivery Date",
]


# ============================================================================
# Private Helper Functions
# ============================================================================


def _normalize_column_name(col_name: str) -> str:
    """
    Normalize a column name for flexible matching by converting to lowercase
    and stripping non-alphanumeric characters.

    Args:
        col_name: Raw column name string.

    Returns:
        str: Cleaned alphanumeric string.
    """
    if not col_name:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(col_name).lower())


def _find_matching_column(df: pd.DataFrame, target_name: str) -> str | None:
    """
    Find an existing column in a DataFrame that matches the target name,
    ignoring case, spaces, and punctuation.

    Args:
        df: Input DataFrame.
        target_name: The column title to search for.

    Returns:
        str | None: The actual matching column name in df, or None if not found.
    """
    target_norm = _normalize_column_name(target_name)
    for col in df.columns:
        if _normalize_column_name(col) == target_norm:
            return str(col)
    return None


def _clean_numeric_series(
    series: pd.Series, fill_value: float = 0.0
) -> pd.Series:
    """
    Clean financial and numeric series by stripping currency symbols, commas,
    abbreviations (e.g. Rs., USD, $), and spaces, then converting to float.

    Args:
        series: Raw Pandas Series.
        fill_value: Value to use for missing or invalid numbers. Defaults to 0.0.

    Returns:
        pd.Series: Cleaned float series.
    """
    if series.empty:
        return pd.Series(dtype=float)

    def _parse_val(val: Any) -> float:
        if pd.isna(val) or val is None or str(val).strip() == "":
            return fill_value
        if isinstance(val, (int, float)):
            return float(val)

        s_val = str(val).strip()
        is_negative = "-" in s_val or ("(" in s_val and ")" in s_val)

        # Extract number sequence with optional commas and optional decimal point
        match = re.search(r"\d+(?:,\d+)*(?:\.\d+)?", s_val)
        if match:
            num_str = match.group(0).replace(",", "")
            try:
                num_float = float(num_str)
                return -num_float if is_negative else num_float
            except ValueError:
                return fill_value

        return fill_value

    return series.apply(_parse_val).astype(float)


def _clean_date_series(series: pd.Series) -> pd.Series:
    """
    Normalize date strings in a series to YYYY-MM-DD format using pd.to_datetime.

    Args:
        series: Raw date series.

    Returns:
        pd.Series: Formatted date string series (YYYY-MM-DD or None/NaT).
    """
    if series.empty:
        return pd.Series(dtype=object)

    parsed = pd.to_datetime(series, errors="coerce")
    # Convert valid dates to YYYY-MM-DD string format
    formatted = parsed.dt.strftime("%Y-%m-%d")
    # Replace NaN/NaT string outputs with None
    return formatted.where(formatted.notna(), None)


def _clean_text_series(
    series: pd.Series, default_val: str = "Unspecified", title_case: bool = False
) -> pd.Series:
    """
    Strip whitespace, handle missing values, and optionally title-case strings in a series.

    Args:
        series: Raw text series.
        default_val: Fallback value for missing/empty entries.
        title_case: Whether to normalize text using title casing.

    Returns:
        pd.Series: Cleaned string series.
    """
    if series.empty:
        return pd.Series(dtype=object)

    def _transform(val: Any) -> str:
        if pd.isna(val) or val is None or str(val).strip() == "":
            return default_val
        s_val = str(val).strip()
        return s_val.title() if title_case else s_val

    return series.apply(_transform).astype(str)


def _build_empty_dataframe(columns: list[str]) -> pd.DataFrame:
    """Helper to build a clean empty DataFrame with expected columns."""
    return pd.DataFrame(columns=columns)


# ============================================================================
# Public Core Functions
# ============================================================================


def clean_deals_data(raw_deals_list: list[dict]) -> pd.DataFrame:
    """
    Clean, normalize, and validate raw Monday.com Deals board data.

    Args:
        raw_deals_list: List of raw dictionaries representing deal items.

    Returns:
        pd.DataFrame: Cleaned DataFrame with standardized column names and types.
    """
    logger.info("Starting clean_deals_data processing on %d raw items.", len(raw_deals_list or []))

    if not raw_deals_list:
        logger.warning("Empty raw_deals_list provided. Returning empty Deals DataFrame.")
        return _build_empty_dataframe(DEALS_CANONICAL_COLUMNS)

    # Avoid mutating input list
    deals_data = copy.deepcopy(raw_deals_list)
    raw_df = pd.DataFrame(deals_data)

    clean_df = pd.DataFrame(index=raw_df.index)

    # 1. Match and extract columns safely without KeyError
    matched_cols = {}
    for target in DEALS_CANONICAL_COLUMNS:
        found_col = _find_matching_column(raw_df, target)
        matched_cols[target] = found_col
        if found_col is not None:
            clean_df[target] = raw_df[found_col]
        else:
            clean_df[target] = None
            logger.debug("Column '%s' not found in raw deals. Defaulting to None.", target)

    # 2. Clean numeric / financial columns
    clean_df["Masked Deal value"] = _clean_numeric_series(
        clean_df["Masked Deal value"], fill_value=0.0
    )
    clean_df["Closure Probability"] = _clean_numeric_series(
        clean_df["Closure Probability"], fill_value=0.0
    )

    # 3. Clean date columns
    for date_col in ["Close Date (A)", "Tentative Close Date", "Created Date"]:
        clean_df[date_col] = _clean_date_series(clean_df[date_col])

    # 4. Clean categorical / text columns
    for text_col in ["Sector/service", "Deal Status", "Deal Stage"]:
        clean_df[text_col] = _clean_text_series(
            clean_df[text_col], default_val="Unspecified", title_case=True
        )

    # Clean id and name
    clean_df["id"] = _clean_text_series(clean_df["id"], default_val="Unspecified")
    clean_df["name"] = _clean_text_series(clean_df["name"], default_val="Unspecified")

    # Reorder to canonical columns
    clean_df = clean_df[DEALS_CANONICAL_COLUMNS]

    logger.info("Successfully cleaned Deals DataFrame with %d rows.", len(clean_df))
    return clean_df


def clean_work_orders_data(raw_wo_list: list[dict]) -> pd.DataFrame:
    """
    Clean, normalize, and validate raw Monday.com Work Orders board data.

    Args:
        raw_wo_list: List of raw dictionaries representing work order items.

    Returns:
        pd.DataFrame: Cleaned DataFrame with standardized column names and types.
    """
    logger.info("Starting clean_work_orders_data processing on %d raw items.", len(raw_wo_list or []))

    if not raw_wo_list:
        logger.warning("Empty raw_wo_list provided. Returning empty Work Orders DataFrame.")
        return _build_empty_dataframe(WORK_ORDERS_CANONICAL_COLUMNS)

    # Avoid mutating input list
    wo_data = copy.deepcopy(raw_wo_list)
    raw_df = pd.DataFrame(wo_data)

    clean_df = pd.DataFrame(index=raw_df.index)

    # 1. Match and extract columns safely
    for target in WORK_ORDERS_CANONICAL_COLUMNS:
        found_col = _find_matching_column(raw_df, target)
        if found_col is not None:
            clean_df[target] = raw_df[found_col]
        else:
            clean_df[target] = None
            logger.debug("Column '%s' not found in raw work orders. Defaulting to None.", target)

    # 2. Clean financial columns
    financial_cols = [
        "Amount in Rupees (Excl of GST) (Masked)",
        "Billed Value in Rupees (Excl of GST.) (Masked)",
    ]
    for fin_col in financial_cols:
        clean_df[fin_col] = _clean_numeric_series(clean_df[fin_col], fill_value=0.0)

    # 3. Clean date columns
    date_cols = ["Probable Start Date", "Probable End Date", "Data Delivery Date"]
    for date_col in date_cols:
        clean_df[date_col] = _clean_date_series(clean_df[date_col])

    # 4. Clean text / categorical columns with "Unknown" default and Title Case
    text_cols = [
        "id",
        "name",
        "Deal name masked",
        "Customer Name Code",
        "Execution Status",
        "Sector",
        "Type of Work",
    ]
    for text_col in text_cols:
        clean_df[text_col] = _clean_text_series(
            clean_df[text_col], default_val="Unknown", title_case=True
        )

    # Reorder to canonical columns
    clean_df = clean_df[WORK_ORDERS_CANONICAL_COLUMNS]

    logger.info("Successfully cleaned Work Orders DataFrame with %d rows.", len(clean_df))
    return clean_df


def generate_data_quality_report(
    deals_df: pd.DataFrame, wo_df: pd.DataFrame
) -> dict[str, Any]:
    """
    Generate a structured data quality audit report detailing record counts,
    missing value metrics, and automatic corrections performed.

    Args:
        deals_df: Cleaned Deals DataFrame.
        wo_df: Cleaned Work Orders DataFrame.

    Returns:
        dict[str, Any]: Structured quality report dictionary suitable for frontend or AI agent.
    """
    logger.info("Generating data quality report for Deals (%d rows) and Work Orders (%d rows).",
                len(deals_df), len(wo_df))

    deals_count = len(deals_df) if deals_df is not None else 0
    wo_count = len(wo_df) if wo_df is not None else 0
    total_records = deals_count + wo_count

    # Calculate missing value counts in Deals
    deals_missing_financial = 0
    deals_missing_close_dates = 0
    if deals_count > 0:
        # Check deals where Masked Deal value is 0.0 or original missing
        deals_missing_financial = int((deals_df["Masked Deal value"] == 0.0).sum())
        # Check deals where Close Date (A) is None / null
        deals_missing_close_dates = int(deals_df["Close Date (A)"].isna().sum())

    # Calculate missing value counts in Work Orders
    wo_missing_exec_status = 0
    wo_missing_financial = 0
    if wo_count > 0:
        # Check work orders where Execution Status is missing or "Unknown"
        wo_missing_exec_status = int(
            (wo_df["Execution Status"].isna() | (wo_df["Execution Status"] == "Unknown")).sum()
        )
        # Check work orders where amount is 0.0
        wo_missing_financial = int(
            (
                (wo_df["Amount in Rupees (Excl of GST) (Masked)"] == 0.0)
                | (wo_df["Billed Value in Rupees (Excl of GST.) (Masked)"] == 0.0)
            ).sum()
        )

    # Compute record completeness metrics
    deals_null_rows = 0
    wo_null_rows = 0
    if deals_count > 0:
        # A row has missing values if any column contains None, NaN, "Unspecified", or 0.0 in financials
        deals_null_rows = int(
            deals_df.isin([None, "Unspecified", "Unknown"]).any(axis=1).sum()
        )
    if wo_count > 0:
        wo_null_rows = int(
            wo_df.isin([None, "Unspecified", "Unknown"]).any(axis=1).sum()
        )

    total_records_with_missing = deals_null_rows + wo_null_rows
    total_complete_records = max(0, total_records - total_records_with_missing)

    complete_pct = (
        round((total_complete_records / total_records) * 100, 2)
        if total_records > 0
        else 100.0
    )
    missing_pct = (
        round((total_records_with_missing / total_records) * 100, 2)
        if total_records > 0
        else 0.0
    )

    # Human-readable caveats
    caveats = [
        "Financial values cleaned of currency symbols, commas, and non-numeric characters; missing values set to 0.0.",
        "Dates normalized to YYYY-MM-DD format; invalid or unparseable dates coerced to None.",
        "Missing text and categorical fields filled with 'Unspecified' (Deals) or 'Unknown' (Work Orders).",
        "Categorical string values trimmed of leading/trailing whitespace and title-cased.",
        "Flexible column name matching applied to handle slight board schema variations without raising KeyError exceptions."
    ]

    report = {
        "total_records": total_records,
        "deals_count": deals_count,
        "work_orders_count": wo_count,
        "complete_records_percentage": complete_pct,
        "missing_values_records_percentage": missing_pct,
        "deals_missing_financial_values": deals_missing_financial,
        "deals_missing_close_dates": deals_missing_close_dates,
        "work_orders_missing_execution_status": wo_missing_exec_status,
        "work_orders_missing_financial_values": wo_missing_financial,
        "caveats": caveats,
    }

    logger.info("Data quality report generated: %s", report)
    return report
