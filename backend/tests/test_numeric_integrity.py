"""
Comprehensive Unit and Regression Tests for Numeric Data Integrity Remediation (Phase 3.3).

Verifies:
1. Missing versus zero distinction (None, NaN, "", "   " vs 0, "0", 0.0)
2. Invalid versus missing distinction ("invalid string", "TBD" vs empty/None)
3. Negative values (-1000, "-1000", "(1000)", "-₹250", "(₹50,000)")
4. Every supported multiplier (Crore, Cr, Lakh, Lac, Million, M, Thousand, K)
5. Foreign currency rejection ($100,000, 100 USD, €500, £250, etc.)
6. Coverage arithmetic invariant: valid_numeric_count + missing_value_count + invalid_value_count == total_records
7. Sum exclusion of missing and invalid records
8. Average OPEN deal denominator correctness (excludes missing and invalid; includes legitimate 0.0)
9. Header artifact exclusion from KPI population and coverage
10. Existing full dataset reconciliation
11. Synthetic dataset containing valid zero, missing value, invalid string, negative value, and positive value across categories
"""

from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.data_cleaner import (
    NumericStatus,
    ParsedNumericValue,
    parse_numeric_value,
    _clean_numeric_series,
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)
from services.analytics_engine import (
    get_pipeline_summary,
    get_revenue_by_sector,
    get_revenue_by_stage,
    get_monthly_pipeline,
)
from services.data_loader import load_from_excel


# =============================================================================
# 1. Missing vs. Zero Distinction Tests
# =============================================================================

def test_missing_versus_zero_distinction():
    """Verify that None, NaN, and empty strings are MISSING, whereas 0, '0', 0.0 are VALID."""
    # Missing cases
    missing_inputs = [None, float("nan"), np.nan, "", "   ", "nan", "None", "NULL"]
    for inp in missing_inputs:
        res = parse_numeric_value(inp)
        assert res.status == NumericStatus.MISSING, f"Expected MISSING for {inp!r}, got {res.status}"
        assert res.value is None, f"Expected None value for {inp!r}, got {res.value}"
        assert res.is_missing is True
        assert res.is_valid is False

    # Valid zero cases
    zero_inputs = [0, 0.0, "0", "0.0", "₹0", "Rs. 0", "  0  "]
    for inp in zero_inputs:
        res = parse_numeric_value(inp)
        assert res.status == NumericStatus.VALID, f"Expected VALID for {inp!r}, got {res.status}"
        assert res.value == 0.0, f"Expected 0.0 value for {inp!r}, got {res.value}"
        assert res.is_valid is True
        assert res.is_missing is False


# =============================================================================
# 2. Invalid vs. Missing Distinction Tests
# =============================================================================

def test_invalid_versus_missing_distinction():
    """Verify that non-numeric strings are INVALID, distinguishable from MISSING."""
    invalid_inputs = [
        "invalid string",
        "TBD",
        "TBA",
        "N/A",
        "pending",
        "100km",
        "minimum 50",
        "maximum",
        "deal status",
        True,
        False,
    ]
    for inp in invalid_inputs:
        res = parse_numeric_value(inp)
        assert res.status == NumericStatus.INVALID, f"Expected INVALID for {inp!r}, got {res.status}"
        assert res.value is None
        assert res.is_invalid is True
        assert res.is_missing is False
        assert res.reason is not None


# =============================================================================
# 3. Negative Value Tests
# =============================================================================

def test_negative_values():
    """Verify negative numbers, parenthesized values, and currency prefixes parse correctly."""
    test_cases = [
        (-1000, -1000.0),
        ("-1000", -1000.0),
        ("(1000)", -1000.0),
        ("-₹250", -250.0),
        ("₹-250", -250.0),
        ("(₹5,00,000)", -500000.0),
        ("Rs. -50,000", -50000.0),
        ("(-2.5 Cr)", -25000000.0),
        ("-100K", -100000.0),
    ]
    for inp, expected in test_cases:
        res = parse_numeric_value(inp)
        assert res.status == NumericStatus.VALID
        assert res.value == expected, f"Failed for {inp}: expected {expected}, got {res.value}"


# =============================================================================
# 4. Multiplier Suffix Tests
# =============================================================================

def test_every_supported_multiplier():
    """Verify all Indian and standard financial multiplier suffixes parse accurately."""
    test_cases = [
        ("1 Crore", 10000000.0),
        ("1.5 crore", 15000000.0),
        ("2.5 Cr", 25000000.0),
        ("10 cr", 100000000.0),
        ("5 Lakh", 500000.0),
        ("2.25 lakh", 225000.0),
        ("5 Lac", 500000.0),
        ("1.2 lac", 120000.0),
        ("1.2 Million", 1200000.0),
        ("2.5m", 2500000.0),
        ("50 Thousand", 50000.0),
        ("100K", 100000.0),
        ("15.5k", 15500.0),
    ]
    for inp, expected in test_cases:
        res = parse_numeric_value(inp)
        assert res.status == NumericStatus.VALID
        assert res.value == expected, f"Failed multiplier {inp}: expected {expected}, got {res.value}"


# =============================================================================
# 5. Foreign Currency Rejection Tests
# =============================================================================

def test_foreign_currency_rejection():
    """Verify foreign currencies (USD, EUR, GBP, JPY) are marked UNSUPPORTED_CURRENCY."""
    foreign_cases = [
        "$100,000",
        "$500",
        "100 USD",
        "50 usd",
        "€1000",
        "500 EUR",
        "250 euro",
        "£1000",
        "500 GBP",
        "100 pounds",
        "¥5000",
        "10000 JPY",
    ]
    for inp in foreign_cases:
        res = parse_numeric_value(inp)
        assert res.status == NumericStatus.UNSUPPORTED_CURRENCY, (
            f"Expected UNSUPPORTED_CURRENCY for {inp}, got {res.status}"
        )
        assert res.value is None
        assert res.is_invalid is True
        assert res.is_valid is False
        assert "Unsupported foreign currency" in res.reason


# =============================================================================
# 6. Value Coverage Arithmetic Invariant
# =============================================================================

def test_coverage_arithmetic_invariant():
    """Verify invariant: valid_numeric_count + missing_value_count + invalid_value_count == total_records."""
    raw_deals = [
        {"name": "Valid Pos", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "100000"},
        {"name": "Valid Zero", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "0"},
        {"name": "Missing None", "Deal Status": "Open", "Deal Stage": "Proposal", "Masked Deal value": None},
        {"name": "Missing Empty", "Deal Status": "Open", "Deal Stage": "Proposal", "Masked Deal value": "   "},
        {"name": "Invalid String", "Deal Status": "Lost", "Deal Stage": "Lost", "Masked Deal value": "TBD"},
        {"name": "Foreign Curr", "Deal Status": "Open", "Deal Stage": "Demo", "Masked Deal value": "$50,000"},
        {"name": "Header Artifact", "Deal Status": "Deal Status", "Deal Stage": "Deal Stage", "Masked Deal value": "1000"},
    ]
    df_deals = clean_deals_data(raw_deals)
    ps = get_pipeline_summary(df_deals)
    vc = ps["value_coverage"]

    # Header artifact is excluded from business opportunities (7 raw - 1 header = 6 valid deals)
    assert vc["total_records"] == 6
    assert vc["valid_numeric_count"] == 2  # "100000" and "0"
    assert vc["missing_value_count"] == 2  # None and "   "
    assert vc["invalid_value_count"] == 2  # "TBD" and "$50,000"

    # Invariant formula
    assert vc["valid_numeric_count"] + vc["missing_value_count"] + vc["invalid_value_count"] == vc["total_records"]
    assert vc["sum_valid_values"] == 100000.0


# =============================================================================
# 7. Sum Exclusion of Missing and Invalid Records
# =============================================================================

def test_sum_exclusion_of_missing_and_invalid_records():
    """Verify missing, invalid, and foreign currency values never contribute to monetary sums."""
    raw_deals = [
        {"name": "D1", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "500000"},
        {"name": "D2", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "invalid text"},
        {"name": "D3", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": None},
        {"name": "D4", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "$1,000,000"},
        {"name": "D5", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": 0},
    ]
    df = clean_deals_data(raw_deals)
    ps = get_pipeline_summary(df)

    # Only D1 (500,000) and D5 (0) are valid
    assert ps["gross_historical_opportunity_value"] == 500000.0
    assert ps["value_coverage"]["sum_valid_values"] == 500000.0


# =============================================================================
# 8. Average Deal Value Denominator Correctness
# =============================================================================

def test_average_open_deal_denominator_correctness():
    """
    Verify average OPEN deal value denominator:
    - Excludes missing values
    - Excludes invalid values
    - Includes legitimate 0.0 values
    - Correctly factors negative values
    """
    raw_deals = [
        {"name": "O1", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "100000"},
        {"name": "O2", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "0"},  # legitimate 0.0
        {"name": "O3", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": None}, # missing -> excluded
        {"name": "O4", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "TBD"}, # invalid -> excluded
        {"name": "O5", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "$200K"}, # foreign -> excluded
        {"name": "O6", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "-20000"}, # negative adjustment
    ]
    df = clean_deals_data(raw_deals)
    ps = get_pipeline_summary(df)

    # Valid OPEN deals: O1 (100000), O2 (0), O6 (-20000) -> 3 deals
    # Sum: 100000 + 0 + (-20000) = 80000
    # Average: 80000 / 3 = 26666.67
    assert ps["active_pipeline_value"] == 80000.0
    assert ps["average_deal_value"] == round(80000.0 / 3, 2)


# =============================================================================
# 9. Header Artifact Exclusion Tests
# =============================================================================

def test_header_artifact_exclusion():
    """Verify repeated header artifacts are excluded from all KPIs and coverage metrics."""
    raw_deals = [
        {"name": "Good Won", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "100000", "Sector/service": "Mining"},
        {"name": "Header 1", "Deal Status": "Deal Status", "Deal Stage": "Deal Stage", "Masked Deal value": "999999", "Sector/service": "Sector/Service"},
        {"name": "Header 2", "Deal Status": "Deal Status", "Deal Stage": "Deal Stage", "Masked Deal value": None, "Sector/service": "Sector/Service"},
    ]
    df = clean_deals_data(raw_deals)
    ps = get_pipeline_summary(df)
    rev_sec = get_revenue_by_sector(df)

    assert ps["total_deals"] == 1
    assert ps["unknown_deal_count"] == 2
    assert ps["gross_historical_opportunity_value"] == 100000.0
    assert "Sector/Service" not in rev_sec
    assert rev_sec.get("Mining") == 100000.0


# =============================================================================
# 10. Synthetic Multi-Category Comprehensive Dataset
# =============================================================================

def test_synthetic_dataset_with_all_states_and_categories():
    """
    Synthetic dataset containing:
    - Valid positive value in WON
    - Valid zero in OPEN
    - Missing value in OPEN
    - Invalid string in LOST
    - Negative value in ON_HOLD
    - Foreign currency in DEAD_OR_ABANDONED
    - Repeated header artifact
    """
    raw_deals = [
        {"name": "Won Deal", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "500000", "Sector/service": "Mining"},
        {"name": "Open Zero", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "0", "Sector/service": "Aviation"},
        {"name": "Open Missing", "Deal Status": "Open", "Deal Stage": "Proposal", "Masked Deal value": None, "Sector/service": "Aviation"},
        {"name": "Lost Invalid", "Deal Status": "Dead", "Deal Stage": "L. Project Lost", "Masked Deal value": "Unclear", "Sector/service": "Railways"},
        {"name": "Hold Negative", "Deal Status": "On Hold", "Deal Stage": "On Hold", "Masked Deal value": "-50000", "Sector/service": "Mining"},
        {"name": "Dead USD", "Deal Status": "Dead", "Deal Stage": "Demo", "Masked Deal value": "$10,000", "Sector/service": "Powerline"},
        {"name": "Header", "Deal Status": "Deal Status", "Deal Stage": "Deal Stage", "Masked Deal value": None, "Sector/service": "Sector/Service"},
    ]
    df = clean_deals_data(raw_deals)
    ps = get_pipeline_summary(df)

    # 1. Total business deals: 7 - 1 = 6
    assert ps["total_deals"] == 6
    assert ps["unknown_deal_count"] == 1

    # 2. Value coverage
    vc = ps["value_coverage"]
    assert vc["total_records"] == 6
    assert vc["valid_numeric_count"] == 3   # 500000 (Won), 0 (Open), -50000 (Hold)
    assert vc["missing_value_count"] == 1   # None (Open)
    assert vc["invalid_value_count"] == 2   # "Unclear" (Lost) + "$10,000" (Dead)
    assert vc["valid_numeric_count"] + vc["missing_value_count"] + vc["invalid_value_count"] == 6

    # 3. Sum of valid values
    # 500000 + 0 + (-50000) = 450000
    assert vc["sum_valid_values"] == 450000.0
    assert ps["gross_historical_opportunity_value"] == 450000.0

    # 4. Active pipeline (OPEN category)
    # Valid open deals: "Open Zero" (0). "Open Missing" is excluded from sum and average denominator.
    assert ps["active_pipeline_value"] == 0.0
    assert ps["average_deal_value"] == 0.0

    # 5. Data Quality Report tracking across all 7 ingested rows
    df_wo = clean_work_orders_data([])
    qr = generate_data_quality_report(df, df_wo)
    assert qr["deals_missing_financial_values"] == 2  # Open Missing + Header
    assert qr["deals_invalid_financial_values"] == 1   # Lost Invalid
    assert qr["deals_unsupported_currency_values"] == 1 # Dead USD
    assert qr["deals_rejected_header_rows"] == 1


# =============================================================================
# 11. Existing Full Dataset Reconciliation
# =============================================================================

def test_real_dataset_reconciliation():
    """Verify that the actual Excel dataset reconciles to exact historical and operational figures."""
    deals, wo, _ = load_from_excel(ROOT_DIR)
    df_deals = clean_deals_data(deals)
    ps = get_pipeline_summary(df_deals)

    # Row counts
    assert len(df_deals) == 346
    assert ps["total_deals"] == 344
    assert ps["unknown_deal_count"] == 2

    # Coverage
    vc = ps["value_coverage"]
    assert vc["total_records"] == 344
    assert vc["valid_numeric_count"] == 165
    assert vc["missing_value_count"] == 179
    assert vc["invalid_value_count"] == 0
    assert vc["valid_numeric_count"] + vc["missing_value_count"] + vc["invalid_value_count"] == 344

    # Financial sums
    assert vc["sum_valid_values"] == 2305518040.91
    assert ps["gross_historical_opportunity_value"] == 2305518040.91
    assert ps["active_pipeline_value"] == 688152293.17
    assert ps["average_deal_value"] == 14641538.15
