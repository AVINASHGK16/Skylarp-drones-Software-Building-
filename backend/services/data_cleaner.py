"""
Module for cleaning, normalizing, and validating Monday.com board data.
This module processes raw dictionary items fetched from Monday.com API into
clean, standardized Pandas DataFrames suitable for analytics pipelines.
"""

import copy
import logging
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import pandas as pd

# Configure module logger
logger = logging.getLogger(__name__)

# Canonical Column Definitions (Preserved for compatibility)
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

# Extended Canonical Columns including explicit classification and numeric parsing fields
DEALS_EXTENDED_COLUMNS = DEALS_CANONICAL_COLUMNS + [
    "Classification",
    "Classification Reason",
    "Masked Deal value_status",
    "Masked Deal value_raw",
    "Masked Deal value_reason",
]

# Documented contract: Skylarp Drones dataset source currency is INR (Indian Rupees)
SOURCE_CURRENCY_CONTRACT = "INR"

# Regex patterns for foreign currencies that must NOT enter INR totals without conversion
FOREIGN_CURRENCY_PATTERNS = [
    (r"\$", "USD"),
    (r"\busd\b", "USD"),
    (r"€", "EUR"),
    (r"\beur(?:o|os)?\b", "EUR"),
    (r"£", "GBP"),
    (r"\bgbp\b|\bpound(?:s)?\b", "GBP"),
    (r"¥", "JPY/CNY"),
    (r"\b(?:jpy|cny)\b", "JPY/CNY"),
    (r"\b(?:aud|cad)\b", "AUD/CAD"),
]


# ============================================================================
# Numeric Value States & Models
# ============================================================================


class NumericStatus(str, Enum):
    """Mutually exclusive numeric parsing states."""

    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"


@dataclass(frozen=True)
class ParsedNumericValue:
    """Explicit parsing outcome preserving numeric value, classification, and diagnostics."""

    value: Optional[float]
    status: str
    raw_value: Any
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.status == NumericStatus.VALID

    @property
    def is_missing(self) -> bool:
        return self.status == NumericStatus.MISSING

    @property
    def is_invalid(self) -> bool:
        return self.status in (NumericStatus.INVALID, NumericStatus.UNSUPPORTED_CURRENCY)


def parse_numeric_value(val: Any) -> ParsedNumericValue:
    """
    Parse an input value into an explicit ParsedNumericValue preserving:
    - Parsed numeric float value (or None if missing, invalid, or unsupported currency)
    - Mutually exclusive status: VALID, MISSING, INVALID, or UNSUPPORTED_CURRENCY
    - Original raw input for diagnostics
    - Diagnostic explanation reason

    Contract:
    - Missing (None, NaN, empty/whitespace string, "nan", "none", "null") -> MISSING
    - Genuine numeric zero (0, 0.0, "0", "0.0") -> VALID (value=0.0)
    - Valid numbers (-1000, 500000.0, "₹5,00,000", "(1000)", "5 Lakh") -> VALID
    - Foreign currencies ($100,000, €500, £250) -> UNSUPPORTED_CURRENCY (value=None)
    - Unparseable text ("invalid", "TBD", "100km") -> INVALID (value=None)
    """
    # 1. Missing: None or pandas/numpy NaN
    if val is None or pd.isna(val):
        return ParsedNumericValue(
            value=None,
            status=NumericStatus.MISSING,
            raw_value=val,
            reason="Missing value (None or NaN)",
        )

    # 2. Boolean check (in Python bool is a subclass of int)
    if isinstance(val, bool):
        return ParsedNumericValue(
            value=None,
            status=NumericStatus.INVALID,
            raw_value=val,
            reason="Boolean literal is not a valid monetary number",
        )

    # 3. Native numeric types
    if isinstance(val, (int, float)):
        if math.isnan(val):
            return ParsedNumericValue(
                value=None,
                status=NumericStatus.MISSING,
                raw_value=val,
                reason="NaN floating-point value",
            )
        return ParsedNumericValue(
            value=float(val),
            status=NumericStatus.VALID,
            raw_value=val,
            reason="Native numeric type",
        )

    # 4. String handling
    s_val = str(val).strip()
    if not s_val or s_val.lower() in ("nan", "none", "null"):
        return ParsedNumericValue(
            value=None,
            status=NumericStatus.MISSING,
            raw_value=val,
            reason="Empty or null string",
        )

    s_lower = s_val.lower()

    # 5. Foreign currency detection (Currency Safety)
    for pattern, curr_code in FOREIGN_CURRENCY_PATTERNS:
        if re.search(pattern, s_lower):
            return ParsedNumericValue(
                value=None,
                status=NumericStatus.UNSUPPORTED_CURRENCY,
                raw_value=val,
                reason=f"Unsupported foreign currency detected [{curr_code}]; INR source contract requires conversion",
            )

    # 6. Negative number check
    is_negative = bool(
        re.search(r"^\s*\(.+\)\s*$", s_val)
        or re.search(r"^\s*-", s_val)
        or re.search(r"^(?:rs\.?|inr|₹)\s*-", s_val, re.IGNORECASE)
        or re.search(r"-\s*(?:rs\.?|inr|₹)", s_val, re.IGNORECASE)
    )

    # 7. Strip domestic INR markers, commas, parentheses, minus signs
    s_clean = re.sub(r"^(?:rs\.?|inr|₹)\s*", "", s_val, flags=re.IGNORECASE).strip()
    s_clean = re.sub(r"^[-\(\s]+", "", s_clean)
    s_clean = re.sub(r"[\)\s]+$", "", s_clean)
    s_clean = re.sub(r"^(?:rs\.?|inr|₹)\s*", "", s_clean, flags=re.IGNORECASE).strip()
    s_clean = s_clean.replace("₹", "").replace(",", "").strip()

    # 8. Check for multipliers
    multipliers = [
        ("crore", 1e7),
        ("cr", 1e7),
        ("lakh", 1e5),
        ("lac", 1e5),
        ("million", 1e6),
        ("m", 1e6),
        ("thousand", 1e3),
        ("k", 1e3),
    ]

    for unit, mult in multipliers:
        pattern = rf"^(\d+(?:\.\d+)?)\s*{unit}$"
        match = re.match(pattern, s_clean.lower())
        if match:
            num = float(match.group(1))
            final_val = -(num * mult) if is_negative else (num * mult)
            return ParsedNumericValue(
                value=final_val,
                status=NumericStatus.VALID,
                raw_value=val,
                reason=f"Parsed numeric with multiplier suffix '{unit}'",
            )

    # 9. Plain number without suffix
    match_full = re.match(r"^(\d+(?:\.\d+)?)$", s_clean)
    if match_full:
        num = float(match_full.group(1))
        final_val = -num if is_negative else num
        return ParsedNumericValue(
            value=final_val,
            status=NumericStatus.VALID,
            raw_value=val,
            reason="Parsed plain numeric string",
        )

    # 10. Unrecognized format
    return ParsedNumericValue(
        value=None,
        status=NumericStatus.INVALID,
        raw_value=val,
        reason=f"Unrecognized numeric string format: '{s_val}'",
    )

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
    series: pd.Series, fill_value: Optional[float] = None
) -> pd.Series:
    """
    Clean financial and numeric series using parse_numeric_value.

    If fill_value is None (default), MISSING, INVALID, and UNSUPPORTED_CURRENCY
    records are coerced to np.nan, preserving distinction with legitimate 0.0 values.
    If fill_value is provided (e.g. 0.0), non-valid values are replaced by fill_value.

    Args:
        series: Raw Pandas Series.
        fill_value: Optional numeric fill value. Defaults to None (preserves np.nan).

    Returns:
        pd.Series: Cleaned float series.
    """
    if series.empty:
        return pd.Series(dtype=float)

    def _convert(v: Any) -> float:
        parsed = parse_numeric_value(v)
        if parsed.is_valid:
            return parsed.value
        return float("nan") if fill_value is None else float(fill_value)

    return series.apply(_convert).astype(float)


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


def classify_deal(status_val: Any, stage_val: Any) -> tuple[str, str]:
    """
    Classify a deal into one of 8 mutually exclusive categories using deterministic rules:
    - WON
    - LOST
    - DEAD_OR_ABANDONED
    - CANCELLED
    - OPEN
    - ON_HOLD
    - UNASSIGNED_INBOUND
    - UNKNOWN_OR_UNCLASSIFIED

    Rules:
    1. Use normalized Deal Status as the primary classification when it contains a recognized business outcome.
    2. Use Deal Stage only as a documented fallback when Deal Status is missing or unrecognized.
    3. Conflicting recognized status and stage are handled deterministically.
    4. Deal Status = Dead and Deal Stage = Project Won is classified as DEAD_OR_ABANDONED.
    5. Deal Status = Won and Deal Stage = Lead Generated remains WON.
    6. Repeated header rows are classified as UNKNOWN_OR_UNCLASSIFIED.
    7. Unknown values are never silently classified as Open.
    """
    status_str = str(status_val).strip() if pd.notna(status_val) and status_val is not None else ""
    stage_str = str(stage_val).strip() if pd.notna(stage_val) and stage_val is not None else ""

    status_lower = status_str.lower()
    stage_lower = stage_str.lower()

    # Rule 6: Header row artifact
    if status_lower in ["deal status"] or stage_lower in ["deal stage"]:
        return "UNKNOWN_OR_UNCLASSIFIED", "Repeated table header row artifact"

    # Rule 4: Dead status overrides Won stage (terminal outcome)
    if "dead" in status_lower and "won" in stage_lower:
        return "DEAD_OR_ABANDONED", "Deal Status is Dead (overrides G. Project Won stage)"

    # Rule 1 & 5: Status Won is authoritative primary classification
    if "won" in status_lower:
        return "WON", "Deal Status is Won (primary outcome)"

    # Rule 1: Status Dead is authoritative
    if "dead" in status_lower:
        if "lost" in stage_lower:
            return "LOST", "Deal Status is Dead with L. Project Lost stage"
        return "DEAD_OR_ABANDONED", "Deal Status is Dead"

    # Rule 1: Status Cancelled
    if "cancel" in status_lower:
        return "CANCELLED", "Deal Status is Cancelled"

    # Rule 1: Status On Hold
    if "on hold" in status_lower or "on-hold" in status_lower:
        return "ON_HOLD", "Deal Status is On Hold"

    # Rule 1: Status Open
    if "open" in status_lower or "in progress" in status_lower or "active" in status_lower:
        return "OPEN", "Deal Status is Open"

    # Rule 2: Fallback to Stage when Deal Status is missing, empty, or unrecognized
    if not status_str or status_lower in ["nan", "none", "unspecified", "unknown"]:
        if "lead" in stage_lower:
            return "UNASSIGNED_INBOUND", "Unassigned inbound lead (missing Deal Status with Lead stage)"
        if "won" in stage_lower:
            return "WON", "Fallback to Deal Stage: Won"
        if "lost" in stage_lower:
            return "LOST", "Fallback to Deal Stage: Lost"
        if "cancel" in stage_lower:
            return "CANCELLED", "Fallback to Deal Stage: Cancelled"
        if "hold" in stage_lower:
            return "ON_HOLD", "Fallback to Deal Stage: On Hold"
        if any(term in stage_lower for term in ["not relevant", "dead", "abandoned"]):
            return "DEAD_OR_ABANDONED", "Fallback to Deal Stage: Not Relevant / Abandoned"
        return "UNKNOWN_OR_UNCLASSIFIED", f"Missing Deal Status with unclassified stage [{stage_str}]"

    # Fallback for unrecognized status string
    if "lost" in stage_lower:
        return "LOST", f"Unrecognized status [{status_str}]; classified via Lost stage"
    if "won" in stage_lower:
        return "WON", f"Unrecognized status [{status_str}]; classified via Won stage"

    return "UNKNOWN_OR_UNCLASSIFIED", f"Unrecognized Deal Status [{status_str}] and Deal Stage [{stage_str}]"


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

    # 2. Clean numeric / financial columns with detailed state preservation
    parsed_deals = clean_df["Masked Deal value"].apply(parse_numeric_value)
    clean_df["Masked Deal value"] = parsed_deals.apply(
        lambda p: p.value if p.is_valid else float("nan")
    ).astype(float)
    clean_df["Masked Deal value_status"] = parsed_deals.apply(lambda p: p.status).astype(str)
    clean_df["Masked Deal value_raw"] = parsed_deals.apply(lambda p: p.raw_value)
    clean_df["Masked Deal value_reason"] = parsed_deals.apply(lambda p: p.reason if p.reason else "").astype(str)

    parsed_closure = clean_df["Closure Probability"].apply(parse_numeric_value)
    clean_df["Closure Probability"] = parsed_closure.apply(
        lambda p: p.value if p.is_valid else float("nan")
    ).astype(float)

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

    # 5. Apply deterministic mutually exclusive deal classification
    classifications = []
    reasons = []
    for _, row in clean_df.iterrows():
        cat, reason = classify_deal(row["Deal Status"], row["Deal Stage"])
        classifications.append(cat)
        reasons.append(reason)

    clean_df["Classification"] = classifications
    clean_df["Classification Reason"] = reasons

    # Reorder to extended columns
    clean_df = clean_df[DEALS_EXTENDED_COLUMNS]

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
        clean_df[fin_col] = _clean_numeric_series(clean_df[fin_col], fill_value=None)

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

    # Calculate missing and invalid value counts in Deals
    deals_missing_financial = 0
    deals_invalid_financial = 0
    deals_unsupported_currency = 0
    deals_missing_close_dates = 0
    if deals_count > 0:
        if "Masked Deal value_status" in deals_df.columns:
            deals_missing_financial = int((deals_df["Masked Deal value_status"] == "MISSING").sum())
            deals_invalid_financial = int((deals_df["Masked Deal value_status"] == "INVALID").sum())
            deals_unsupported_currency = int((deals_df["Masked Deal value_status"] == "UNSUPPORTED_CURRENCY").sum())
        else:
            deals_missing_financial = int(deals_df["Masked Deal value"].isna().sum())
        deals_missing_close_dates = int(deals_df["Close Date (A)"].isna().sum())

    # Calculate missing value counts in Work Orders
    wo_missing_exec_status = 0
    wo_missing_financial = 0
    if wo_count > 0:
        wo_missing_exec_status = int(
            (wo_df["Execution Status"].isna() | (wo_df["Execution Status"] == "Unknown")).sum()
        )
        wo_missing_financial = int(
            (
                wo_df["Amount in Rupees (Excl of GST) (Masked)"].isna()
                | wo_df["Billed Value in Rupees (Excl of GST.) (Masked)"].isna()
            ).sum()
        )

    # Compute record completeness metrics
    deals_null_rows = 0
    wo_null_rows = 0
    if deals_count > 0:
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
        "Financial values parsed with explicit status preservation (VALID, MISSING, INVALID, UNSUPPORTED_CURRENCY); missing and invalid values are excluded from sums, and unsupported foreign currencies are preserved in diagnostics without conversion.",
        "Dates normalized to YYYY-MM-DD format; invalid or unparseable dates coerced to None.",
        "Missing text and categorical fields filled with 'Unspecified' (Deals) or 'Unknown' (Work Orders).",
        "Categorical string values trimmed of leading/trailing whitespace and title-cased.",
        "Flexible column name matching applied to handle slight board schema variations without raising KeyError exceptions."
    ]

    # Track classification counts, rejected header rows, and conflicting records in Deals
    rejected_header_rows = 0
    conflicting_records_count = 0
    classification_breakdown = {}

    if deals_count > 0 and "Classification" in deals_df.columns:
        classification_counts = deals_df["Classification"].value_counts().to_dict()
        classification_breakdown = {str(k): int(v) for k, v in classification_counts.items()}
        rejected_header_rows = int((deals_df["Classification"] == "UNKNOWN_OR_UNCLASSIFIED").sum())

        # Track conflicting records (e.g. Dead status with Won stage)
        if "Classification Reason" in deals_df.columns:
            conflicting_records_count = int(
                deals_df["Classification Reason"].str.contains("overrides", case=False, na=False).sum()
            )

    report = {
        "total_records": total_records,
        "deals_count": deals_count,
        "work_orders_count": wo_count,
        "complete_records_percentage": complete_pct,
        "missing_values_records_percentage": missing_pct,
        "deals_missing_financial_values": deals_missing_financial,
        "deals_invalid_financial_values": deals_invalid_financial,
        "deals_unsupported_currency_values": deals_unsupported_currency,
        "deals_missing_close_dates": deals_missing_close_dates,
        "deals_rejected_header_rows": rejected_header_rows,
        "deals_conflicting_records_count": conflicting_records_count,
        "deals_classification_breakdown": classification_breakdown,
        "work_orders_missing_execution_status": wo_missing_exec_status,
        "work_orders_missing_financial_values": wo_missing_financial,
        "caveats": caveats,
    }

    logger.info("Data quality report generated: %s", report)
    return report
