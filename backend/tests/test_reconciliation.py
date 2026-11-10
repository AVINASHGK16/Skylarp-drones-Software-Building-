"""
Comprehensive Regression Tests for Deal Classification, KPI Calculations, and Numeric Parsing.
Verifies all findings and requirements from Phase 3.2 and DEAL_RECONCILIATION.md:
- Dead status + Won stage
- Won status + Lead Generated stage
- Missing status + recognized stage
- Conflicting status and stage
- Cancelled deals
- On Hold deals
- Unassigned inbound leads
- Repeated header rows
- Unknown statuses
- Missing, invalid, and actual zero values
- All numeric suffix examples (₹5,00,000, 5 Lakh, 5 Lac, 1.5 Crore, 2.5 Cr, 100K, 1.2M, 1000, -₹250, (1000))
- Zero-denominator win rates
- Exact reconciliation of classification counts and monetary values against real Excel dataset
"""

from pathlib import Path
import sys
import pandas as pd
import pytest

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.data_cleaner import (
    _clean_numeric_series,
    classify_deal,
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
    parse_numeric_value,
    NumericStatus,
)
from services.analytics_engine import get_pipeline_summary
from services.data_loader import load_from_excel


# =============================================================================
# 1. Numeric Parser Tests
# =============================================================================

def test_numeric_parser_all_required_cases():
    """Verify all required numeric strings and suffixes parse to exact floats with parse_numeric_value."""
    test_cases = [
        ("₹5,00,000", 500000.0, NumericStatus.VALID),
        ("5 Lakh", 500000.0, NumericStatus.VALID),
        ("5 Lac", 500000.0, NumericStatus.VALID),
        ("1.5 Crore", 15000000.0, NumericStatus.VALID),
        ("2.5 Cr", 25000000.0, NumericStatus.VALID),
        ("100K", 100000.0, NumericStatus.VALID),
        ("1.2M", 1200000.0, NumericStatus.VALID),
        ("1000", 1000.0, NumericStatus.VALID),
        ("-₹250", -250.0, NumericStatus.VALID),
        ("(1000)", -1000.0, NumericStatus.VALID),
        ("Rs. 50,000.00", 50000.0, NumericStatus.VALID),
        ("$100,000", None, NumericStatus.UNSUPPORTED_CURRENCY),
        ("", None, NumericStatus.MISSING),
        ("   ", None, NumericStatus.MISSING),
        (None, None, NumericStatus.MISSING),
        ("invalid string", None, NumericStatus.INVALID),
        ("deal status", None, NumericStatus.INVALID),
    ]

    for inp, expected_val, expected_status in test_cases:
        res = parse_numeric_value(inp)
        assert res.status == expected_status, f"Failed status on input {inp}: expected {expected_status}, got {res.status}"
        if expected_val is not None:
            assert res.value == expected_val, f"Failed value on input {inp}: expected {expected_val}, got {res.value}"
        else:
            assert res.value is None, f"Expected None value on input {inp}, got {res.value}"


def test_numeric_parser_avoids_matching_m_inside_words():
    """Ensure suffixes like 'm' or 'k' are not matched inside arbitrary words."""
    test_cases = [
        ("minimum 50", 0.0),
        ("100km", 0.0),
        ("maximum", 0.0),
    ]
    s = pd.Series([tc[0] for tc in test_cases])
    res = _clean_numeric_series(s, fill_value=0.0)
    for (inp, expected), actual in zip(test_cases, res):
        assert actual == expected


# =============================================================================
# 2. Deal Classification Rule Tests
# =============================================================================

def test_classify_dead_status_with_won_stage():
    """Rule 4: Deal Status = Dead and Deal Stage = Project Won must be classified as DEAD_OR_ABANDONED."""
    cat, reason = classify_deal(status_val="Dead", stage_val="G. Project Won")
    assert cat == "DEAD_OR_ABANDONED"
    assert "overrides" in reason.lower()


def test_classify_won_status_with_lead_generated_stage():
    """Rule 5: Deal Status = Won and Deal Stage = Lead Generated must remain WON."""
    cat, reason = classify_deal(status_val="Won", stage_val="A. Lead Generated")
    assert cat == "WON"
    assert "primary outcome" in reason.lower()


def test_classify_missing_status_with_recognized_stage():
    """Rule 2: When Deal Status is missing, fallback to recognized Deal Stage."""
    # Lead stage -> UNASSIGNED_INBOUND
    cat1, _ = classify_deal(status_val=None, stage_val="A. Lead Generated")
    assert cat1 == "UNASSIGNED_INBOUND"

    cat2, _ = classify_deal(status_val="", stage_val="G. Project Won")
    assert cat2 == "WON"

    cat3, _ = classify_deal(status_val="Unspecified", stage_val="L. Project Lost")
    assert cat3 == "LOST"

    cat4, _ = classify_deal(status_val=None, stage_val="M. Projects On Hold")
    assert cat4 == "ON_HOLD"


def test_classify_cancelled_deals():
    """Cancelled status or stage must be classified as CANCELLED."""
    cat1, _ = classify_deal(status_val="Cancelled", stage_val="Negotiations")
    assert cat1 == "CANCELLED"

    cat2, _ = classify_deal(status_val="Unspecified", stage_val="Project Cancelled")
    assert cat2 == "CANCELLED"


def test_classify_on_hold_deals():
    """On Hold status or stage must be classified as ON_HOLD."""
    cat1, _ = classify_deal(status_val="On Hold", stage_val="Proposal Sent")
    assert cat1 == "ON_HOLD"

    cat2, _ = classify_deal(status_val="On-Hold", stage_val="M. Projects On Hold")
    assert cat2 == "ON_HOLD"


def test_classify_unassigned_inbound():
    """Missing status with Lead stage is UNASSIGNED_INBOUND."""
    cat, _ = classify_deal(status_val="", stage_val="A. Lead Generated")
    assert cat == "UNASSIGNED_INBOUND"


def test_classify_repeated_header_rows():
    """Repeated header rows must be UNKNOWN_OR_UNCLASSIFIED."""
    cat, reason = classify_deal(status_val="Deal Status", stage_val="Deal Stage")
    assert cat == "UNKNOWN_OR_UNCLASSIFIED"
    assert "header" in reason.lower()


def test_classify_unknown_status_never_silently_open():
    """Unknown statuses must not silently default to OPEN."""
    cat, _ = classify_deal(status_val="Unrecognized_XYZ", stage_val="Unknown_ABC")
    assert cat == "UNKNOWN_OR_UNCLASSIFIED"
    assert cat != "OPEN"


# =============================================================================
# 3. Pipeline Summary & KPI Metric Tests
# =============================================================================

def test_pipeline_summary_with_synthetic_fixtures():
    """Verify calculation of operational pipeline metrics, win rates, and coverage."""
    raw_deals = [
        {"name": "Won A", "Deal Status": "Won", "Deal Stage": "Won", "Masked Deal value": "100000"},
        {"name": "Won B", "Deal Status": "Won", "Deal Stage": "Lead Generated", "Masked Deal value": None}, # missing val
        {"name": "Lost A", "Deal Status": "Dead", "Deal Stage": "L. Project Lost", "Masked Deal value": "50000"},
        {"name": "Dead A", "Deal Status": "Dead", "Deal Stage": "Demo Done", "Masked Deal value": "25000"},
        {"name": "Dead Won Conflicting", "Deal Status": "Dead", "Deal Stage": "G. Project Won", "Masked Deal value": "10000"},
        {"name": "Open A", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "80000"},
        {"name": "Open B", "Deal Status": "Open", "Deal Stage": "Proposal Sent", "Masked Deal value": "40000"},
        {"name": "On Hold A", "Deal Status": "On Hold", "Deal Stage": "On Hold", "Masked Deal value": "15000"},
        {"name": "Inbound A", "Deal Status": None, "Deal Stage": "A. Lead Generated", "Masked Deal value": None},
        {"name": "Header Artifact", "Deal Status": "Deal Status", "Deal Stage": "Deal Stage", "Masked Deal value": None},
    ]

    df_clean = clean_deals_data(raw_deals)
    ps = get_pipeline_summary(df_clean)

    # 1. Operational Category Counts
    assert ps["won_deal_count"] == 2
    assert ps["lost_deal_count"] == 1
    assert ps["dead_or_abandoned_deal_count"] == 2  # Dead A + Dead Won Conflicting
    assert ps["open_deal_count"] == 2
    assert ps["on_hold_deal_count"] == 1
    assert ps["unassigned_inbound_count"] == 1
    assert ps["cancelled_deal_count"] == 0
    assert ps["unknown_deal_count"] == 1  # Header row

    # 2. Operational Values
    # Active pipeline: Open A (80k) + Open B (40k) = 120k
    assert ps["active_pipeline_value"] == 120000.0

    # Gross historical opportunity: Won A (100k) + Lost A (50k) + Dead A (25k) + Dead Won (10k) + Open A (80k) + Open B (40k) + On Hold (15k) = 320k
    # Note: Header row artifact is excluded from gross opportunity!
    assert ps["gross_historical_opportunity_value"] == 320000.0

    # 3. Win Rates
    # Concluded: Won (2) + Lost (1) + Dead (2) + Cancelled (0) = 5
    # Overall concluded win rate: 2 / 5 * 100 = 40.0%
    assert ps["overall_concluded_win_rate"] == 40.0

    # Formal decision: Won (2) + Lost (1) = 3
    # Formal decision win rate: 2 / 3 * 100 = 66.67%
    assert ps["formal_decision_win_rate"] == 66.67

    # 4. Value Coverage
    # Total valid records: 9 (10 raw minus 1 header artifact)
    # Valid numeric: Won A, Lost A, Dead A, Dead Won, Open A, Open B, On Hold A = 7 records
    # Missing: Won B, Inbound A = 2 records
    vc = ps["value_coverage"]
    assert vc["total_records"] == 9
    assert vc["valid_numeric_count"] == 7
    assert vc["missing_value_count"] == 2
    assert vc["sum_valid_values"] == 320000.0


def test_zero_denominator_win_rates_return_none():
    """When no concluded deals exist, win rates must return None rather than 0.0 or ZeroDivisionError."""
    deals_open_only = [
        {"name": "Open 1", "Deal Status": "Open", "Deal Stage": "Negotiations", "Masked Deal value": "10000"},
        {"name": "Open 2", "Deal Status": "Open", "Deal Stage": "Discovery", "Masked Deal value": "20000"},
    ]
    df_clean = clean_deals_data(deals_open_only)
    ps = get_pipeline_summary(df_clean)

    assert ps["won_deal_count"] == 0
    assert ps["overall_concluded_win_rate"] is None
    assert ps["formal_decision_win_rate"] is None


# =============================================================================
# 4. Full Dataset Reconciliation Regression Test
# =============================================================================

def test_full_reconciliation_against_real_dataset():
    """
    Assert exact counts, values, and win rates against the real Monday.com Excel backup
    matching DEAL_RECONCILIATION.md findings.
    """
    deals, wo, _ = load_from_excel(ROOT_DIR)
    df_deals = clean_deals_data(deals)
    ps = get_pipeline_summary(df_deals)

    # 1. Total Raw and Valid Records
    assert len(df_deals) == 346
    assert ps["unknown_deal_count"] == 2  # 2 repeated header rows
    assert ps["total_deals"] == 344       # 344 valid business opportunities

    # 2. Mutually Exclusive Category Counts (344 valid deals)
    assert ps["won_deal_count"] == 165
    assert ps["lost_deal_count"] == 42
    assert ps["dead_or_abandoned_deal_count"] == 85
    assert ps["open_deal_count"] == 49
    assert ps["open_valued_deal_count"] == 47
    assert ps["on_hold_deal_count"] == 2
    assert ps["unassigned_inbound_count"] == 1
    assert ps["cancelled_deal_count"] == 0

    total_accounted = (
        ps["won_deal_count"]
        + ps["lost_deal_count"]
        + ps["dead_or_abandoned_deal_count"]
        + ps["open_deal_count"]
        + ps["on_hold_deal_count"]
        + ps["unassigned_inbound_count"]
        + ps["cancelled_deal_count"]
    )
    assert total_accounted == 344

    # 3. Exact Reconciled Monetary Values
    # Active pipeline value = sum of 49 Open deals
    assert ps["active_pipeline_value"] == 688152293.17

    # Gross historical opportunity value = ₹230.55 Crore
    assert ps["gross_historical_opportunity_value"] == 2305518040.91

    # 4. Reconciled Win Rates
    # Overall concluded win rate: 165 / (165 + 42 + 85) = 165 / 292 = 56.51%
    assert ps["overall_concluded_win_rate"] == 56.51

    # Formal decision win rate: 165 / (165 + 42) = 165 / 207 = 79.71%
    assert ps["formal_decision_win_rate"] == 79.71

    # 5. Value Coverage
    vc = ps["value_coverage"]
    assert vc["total_records"] == 344
    assert vc["valid_numeric_count"] == 165
    assert vc["missing_value_count"] == 179
    assert vc["sum_valid_values"] == 2305518040.91

    # 6. Data Quality Report Tracking
    df_wo = clean_work_orders_data(wo)
    qr = generate_data_quality_report(df_deals, df_wo)
    assert qr["deals_rejected_header_rows"] == 2
    assert qr["deals_conflicting_records_count"] == 1  # Row 178 (Dead overrides Won)

