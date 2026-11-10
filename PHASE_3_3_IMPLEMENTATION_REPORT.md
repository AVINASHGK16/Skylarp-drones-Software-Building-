# Phase 3.3 — Numeric Data Integrity Remediation Report

**Status:** Complete  
**Date:** 2026-11-09  
**Scope:** `backend/services/data_cleaner.py`, `backend/services/analytics_engine.py`, `backend/tests/`

---

## 1. Executive Summary

In Phase 3.2.3, the audit established that missing values (`None`, `NaN`, `""`), unparseable text (`"invalid"`, `"TBD"`), and legitimate zero values (`0`, `"0"`, `0.0`) were all coerced to `0.0` by `_clean_numeric_series`. This caused severe information loss, prevented legitimate zero-value contracts from being distinguished from unestimated deals, and resulted in hardcoded/inaccurate coverage metrics. Additionally, dollar signs (`$`) were silently stripped without exchange rate conversion.

Phase 3.3 remediates these flaws by:
1. Introducing an explicit `parse_numeric_value()` contract returning a `ParsedNumericValue` dataclass with mutually exclusive states: `VALID`, `MISSING`, `INVALID`, and `UNSUPPORTED_CURRENCY`.
2. Preserving missing and invalid states in cleaned DataFrames as `NaN` (rather than `0.0`), alongside explicit auxiliary status (`Masked Deal value_status`), raw inputs (`Masked Deal value_raw`), and diagnostic reasons (`Masked Deal value_reason`).
3. Enforcing currency safety: rejecting foreign currencies (`USD`, `$`, `EUR`, `€`, `GBP`, `£`) from entering INR financial sums without conversion.
4. Implementing the exact coverage invariant: `valid_numeric_count + missing_value_count + invalid_value_count == total_records`.
5. Ensuring the average OPEN deal denominator strictly excludes missing and invalid records while retaining legitimate ₹0.0 contracts.
6. Excluding repeated header artifacts consistently across pipeline summaries, sectoral revenue, and stage distributions.

---

## 2. Files Changed

| File | Status | Description of Changes |
|---|---|---|
| `backend/services/data_cleaner.py` | Modified | Introduced `NumericStatus` enum, `ParsedNumericValue` dataclass, and `parse_numeric_value()`. Updated `_clean_numeric_series()` to default to `None` fill (preserving `NaN`). Updated `clean_deals_data()` to preserve value status, raw value, and reason columns. Updated `generate_data_quality_report()` to track missing, invalid, and unsupported currency values separately. |
| `backend/services/analytics_engine.py` | Modified | Rewrote `get_pipeline_summary()` value coverage calculation using preserved value states; enforced invariant `valid + missing + invalid == total_records`; ensured only `VALID` numbers contribute to monetary sums; updated `average_deal_value` to compute mean across open valid opportunities; filtered out header row artifacts from `get_revenue_by_sector()`, `get_revenue_by_stage()`, and `get_monthly_pipeline()`. |
| `backend/tests/test_data_cleaner.py` | Modified | Updated test assertions to verify that missing values produce `NaN` and `MISSING` status (not `0.0`), and added test for foreign currency rejection (`UNSUPPORTED_CURRENCY`). |
| `backend/tests/test_analytics_engine.py` | Modified | Updated fixture deal value to INR format (`₹100,000`). |
| `backend/tests/test_reconciliation.py` | Modified | Updated `test_numeric_parser_all_required_cases` to verify explicit `ParsedNumericValue` statuses and values. |
| `backend/tests/test_numeric_integrity.py` | Created | Added 11 comprehensive regression tests covering all Phase 3.3 requirements and synthetic multi-category datasets. |

---

## 3. New Parsing Contract

### 3.1 States and Type Representations

```python
class NumericStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"

@dataclass(frozen=True)
class ParsedNumericValue:
    value: Optional[float]      # float if VALID, else None
    status: str                 # VALID, MISSING, INVALID, or UNSUPPORTED_CURRENCY
    raw_value: Any              # Original raw input
    reason: Optional[str] = None # Diagnostic explanation
```

### 3.2 State Mapping Rules

| Raw Input | Parsed Value | Status | Reason / Description |
|---|---|---|---|
| `None` | `None` | `MISSING` | Missing value (None or NaN) |
| `float("nan")` / `np.nan` | `None` | `MISSING` | NaN floating-point value |
| `""` (empty string) | `None` | `MISSING` | Empty or null string |
| `"   "` (whitespace-only) | `None` | `MISSING` | Empty or null string |
| `"invalid string"` | `None` | `INVALID` | Unrecognized numeric string format |
| `"TBD"` / `"N/A"` | `None` | `INVALID` | Unrecognized numeric string format |
| `True` / `False` | `None` | `INVALID` | Boolean literal is not a monetary number |
| `"0"` / `0` / `0.0` | `0.0` | `VALID` | Legitimate numeric zero |
| `-1000` / `"-1000"` | `-1000.0` | `VALID` | Negative integer |
| `"(1000)"` / `"-₹250"` | `-1000.0` / `-250.0` | `VALID` | Parenthesized or prefixed negative INR |
| `"₹5,00,000"` | `500000.0` | `VALID` | Domestic INR currency formatting |
| `"5 Lakh"` / `"5 Lac"` | `500000.0` | `VALID` | Multiplier suffix $10^5$ |
| `"1.5 Crore"` / `"2.5 Cr"` | `15000000.0` / `25000000.0` | `VALID` | Multiplier suffix $10^7$ |
| `"100K"` / `"1.2M"` | `100000.0` / `1200000.0` | `VALID` | Standard multipliers ($10^3$, $10^6$) |
| `"$100,000"` / `"100 USD"` | `None` | `UNSUPPORTED_CURRENCY` | USD foreign currency rejected from INR totals |
| `"€500"` / `"500 EUR"` | `None` | `UNSUPPORTED_CURRENCY` | EUR foreign currency rejected from INR totals |
| `"£250"` / `"250 GBP"` | `None` | `UNSUPPORTED_CURRENCY` | GBP foreign currency rejected from INR totals |

---

## 4. Value Coverage Before and After

Across the real Excel dataset (`Deal funnel Data.xlsx`, 346 ingested rows):

| Coverage Metric | Phase 3.2 (Previous) | Phase 3.3 (Remediated) | Status & Correctness Notes |
|---|---:|---:|---|
| Total Ingested Deals | 346 | 346 | Exact row preservation |
| Excluded Header Rows | 2 | 2 | Excel rows 50 and 179 |
| **Analyzed Business Deals (`total_records`)** | **344** | **344** | Retained business opportunities |
| **`valid_numeric_count`** | 165 | **165** | Confirmed by explicit `VALID` status |
| **`missing_value_count`** | 179 | **179** | Confirmed by explicit `MISSING` status |
| **`invalid_value_count`** | 0 (hardcoded) | **0** | Calculated dynamically; no invalid entries in source dataset |
| **`sum_valid_values`** | ₹2,305,518,040.91 | **₹2,305,518,040.91** | Sum of only `VALID` numeric records |
| **Coverage Invariant** | Not strictly enforced | **165 + 179 + 0 == 344** | Invariant formula verified and asserted |

---

## 5. Currency Handling Behavior

1. **Documented Source Contract:**  
   The source currency is explicitly established as `INR` (`SOURCE_CURRENCY_CONTRACT = "INR"`), matching the documented Work Orders contract header `(in Rupees (Excl of GST))`. Unmarked numbers and domestic markers (`₹`, `rs.`, `rs`, `inr`) are parsed as INR.
2. **Foreign Currency Rejection:**  
   Inputs with foreign currency indicators (`$`, `USD`, `€`, `EUR`, `£`, `GBP`, `¥`, `JPY`, `CNY`, `AUD`, `CAD`) are **never silently stripped**.
3. **Preservation & Exclusion:**  
   Foreign currency values receive `status = "UNSUPPORTED_CURRENCY"`, `value = None`, and are excluded from INR opportunity sums (`sum_valid_values`, `gross_opportunity_val`, `active_pipeline_val`). The raw string is preserved in `Masked Deal value_raw` and diagnostic details are recorded in `Masked Deal value_reason` and the data quality report (`deals_unsupported_currency_values`).

---

## 6. KPI Before-and-After Comparisons

### 6.1 Real Excel Dataset KPI Comparison

| KPI Metric | Phase 3.2 | Phase 3.3 | Change Explanation |
|---|---:|---:|---|
| Gross Historical Opportunity Value | ₹2,305,518,040.91 | ₹2,305,518,040.91 | Unchanged; 165 valid positive deals |
| Active Pipeline Value | ₹688,152,293.17 | ₹688,152,293.17 | Unchanged; 47 open deals with valid positive values |
| Open Deal Count | 49 | 49 | Mutually exclusive category count |
| Average Open Deal Value | ₹14,641,538.15 | ₹14,641,538.15 | Denominator is 47 (excludes 2 missing open deals) |
| Won Deal Count | 165 | 165 | Mutually exclusive category count |
| Lost Deal Count | 42 | 42 | Mutually exclusive category count |
| Dead or Abandoned Count | 85 | 85 | Mutually exclusive category count |
| On Hold Deal Count | 2 | 2 | Mutually exclusive category count |
| Unassigned Inbound Count | 1 | 1 | Mutually exclusive category count |
| Overall Concluded Win Rate | 56.51% | 56.51% | $165 / (165 + 42 + 85) = 165 / 292$ |
| Formal Decision Win Rate | 79.71% | 79.71% | $165 / (165 + 42) = 165 / 207$ |
| Revenue Breakdown by Sector | 13 sectors (included `"Sector/Service": 0.0`) | **12 sectors** | Repeated header artifact excluded |
| Revenue Breakdown by Stage | 17 stages (included `"Deal Stage": 0.0`) | **16 stages** | Repeated header artifact excluded |

### 6.2 Zero-Value and Missing-Value Behavior in Average Open Deal Value
- In Phase 3.2, missing values were coerced to `0.0`, requiring an ad-hoc filter `numeric_vals > 0` to compute the average. This meant that a legitimate ₹0 deal would have been silently excluded from the average.
- In Phase 3.3, missing and invalid values have `value = None` and `status != "VALID"`. Legitimate zero-value deals (`0.0`) have `status == "VALID"`. The average OPEN deal value is computed over all open deals with `status == "VALID"`. Consequently:
  - Legitimate ₹0 deals remain in the denominator.
  - Missing and invalid deals are excluded from the denominator.
  - Negative values (adjustments/rebates) are included in the sum and denominator.

---

## 7. Test Results

The complete backend test suite and verification scripts were executed:

### 7.1 Pytest Suite
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0 -- backend/venv/Scripts/python.exe
collected 51 items

backend/tests/test_analytics_engine.py::test_empty_analytics PASSED      [  1%]
backend/tests/test_analytics_engine.py::test_populated_analytics PASSED  [  3%]
backend/tests/test_api.py::test_api_endpoints PASSED                     [  5%]
backend/tests/test_bi_agent.py::test_bi_agent_init PASSED                [  7%]
backend/tests/test_bi_agent.py::test_build_context PASSED                [  9%]
backend/tests/test_bi_agent.py::test_answer_question_mocked PASSED       [ 11%]
backend/tests/test_bi_agent.py::test_generate_leadership_report_mocked PASSED [ 13%]
backend/tests/test_bi_agent.py::test_empty_or_blocked_response_fallback PASSED [ 15%]
backend/tests/test_data_cleaner.py::test_empty_inputs PASSED             [ 17%]
backend/tests/test_data_cleaner.py::test_clean_deals PASSED              [ 19%]
backend/tests/test_data_cleaner.py::test_clean_work_orders PASSED        [ 21%]
backend/tests/test_data_cleaner.py::test_quality_report PASSED           [ 23%]
backend/tests/test_fallback.py::test_1_successful_monday_api_fetch PASSED [ 25%]
backend/tests/test_fallback.py::test_2_monday_http_500_excel_fallback PASSED [ 27%]
backend/tests/test_fallback.py::test_3_monday_timeout_excel_fallback PASSED [ 29%]
backend/tests/test_fallback.py::test_4_monday_graphql_error_excel_fallback PASSED [ 31%]
backend/tests/test_fallback.py::test_5_missing_credentials_direct_excel PASSED [ 33%]
backend/tests/test_fallback.py::test_6_missing_excel_file_after_api_failure PASSED [ 35%]
backend/tests/test_fallback.py::test_7_corrupted_excel_file_after_api_failure PASSED [ 37%]
backend/tests/test_fallback.py::test_8_both_sources_failing_natural_startup_and_503 PASSED [ 39%]
backend/tests/test_fallback.py::test_9_metadata_timestamp_semantics PASSED [ 41%]
backend/tests/test_fallback.py::test_10_missing_inaccessible_board_triggers_fallback PASSED [ 43%]
backend/tests/test_fallback.py::test_11_existing_board_with_zero_items_accepted_as_live PASSED [ 45%]
backend/tests/test_fallback.py::test_12_malformed_response_structure_raises_error PASSED [ 47%]
backend/tests/test_fallback.py::test_13_security_sanitization_paths_tokens_and_headers PASSED [ 49%]
backend/tests/test_fallback.py::test_14_health_liveness_vs_readiness PASSED [ 50%]
backend/tests/test_fallback.py::test_15_exact_data_status_json_schema PASSED [ 52%]
backend/tests/test_numeric_integrity.py::test_missing_versus_zero_distinction PASSED [ 54%]
backend/tests/test_numeric_integrity.py::test_invalid_versus_missing_distinction PASSED [ 56%]
backend/tests/test_numeric_integrity.py::test_negative_values PASSED     [ 58%]
backend/tests/test_numeric_integrity.py::test_every_supported_multiplier PASSED [ 60%]
backend/tests/test_numeric_integrity.py::test_foreign_currency_rejection PASSED [ 62%]
backend/tests/test_numeric_integrity.py::test_coverage_arithmetic_invariant PASSED [ 64%]
backend/tests/test_numeric_integrity.py::test_sum_exclusion_of_missing_and_invalid_records PASSED [ 66%]
backend/tests/test_numeric_integrity.py::test_average_open_deal_denominator_correctness PASSED [ 68%]
backend/tests/test_numeric_integrity.py::test_header_artifact_exclusion PASSED [ 70%]
backend/tests/test_numeric_integrity.py::test_synthetic_dataset_with_all_states_and_categories PASSED [ 72%]
backend/tests/test_numeric_integrity.py::test_real_dataset_reconciliation PASSED [ 74%]
backend/tests/test_reconciliation.py::test_numeric_parser_all_required_cases PASSED [ 76%]
backend/tests/test_reconciliation.py::test_numeric_parser_avoids_matching_m_inside_words PASSED [ 78%]
backend/tests/test_reconciliation.py::test_classify_dead_status_with_won_stage PASSED [ 80%]
backend/tests/test_reconciliation.py::test_classify_won_status_with_lead_generated_stage PASSED [ 82%]
backend/tests/test_reconciliation.py::test_classify_missing_status_with_recognized_stage PASSED [ 84%]
backend/tests/test_reconciliation.py::test_classify_cancelled_deals PASSED [ 86%]
backend/tests/test_reconciliation.py::test_classify_on_hold_deals PASSED [ 88%]
backend/tests/test_reconciliation.py::test_classify_unassigned_inbound PASSED [ 90%]
backend/tests/test_reconciliation.py::test_classify_repeated_header_rows PASSED [ 92%]
backend/tests/test_reconciliation.py::test_classify_unknown_status_never_silently_open PASSED [ 94%]
backend/tests/test_reconciliation.py::test_pipeline_summary_with_synthetic_fixtures PASSED [ 96%]
backend/tests/test_reconciliation.py::test_zero_denominator_win_rates_return_none PASSED [ 98%]
backend/tests/test_reconciliation.py::test_full_reconciliation_against_real_dataset PASSED [100%]

======================= 51 passed, 8 warnings in 9.91s ========================
```

### 7.2 Pipeline Verification Script (`verify_pipeline.py`)
Executed cleanly with code 0:
- Loaded 346 deals and 176 work orders.
- Evaluated 344 valid business deals.
- Reported `deals_rejected_header_rows: 2`, `deals_missing_financial_values: 181`, `deals_invalid_financial_values: 0`.
- Gross historical opportunity value: ₹2,305,518,040.91.
- Active pipeline value: ₹688,152,293.17.
- Average deal value: ₹14,641,538.15.
- Excluded bogus `"Sector/Service"` and `"Deal Stage"` artifacts from sector and stage distributions.

---

## 8. Remaining Assumptions or Limitations

1. **Fixed Source Currency Assumption:**  
   The application assumes all unmarked numeric figures in Monday.com or Excel are denominated in INR (Indian Rupee) based on the business contract declared in the Work Orders board header. Multi-currency environments requiring live FX conversions (e.g., dynamically converting USD to INR using daily exchange rates) are not currently supported; foreign currencies are rejected with `UNSUPPORTED_CURRENCY`.
2. **Work Orders Currency Matching:**  
   Work orders explicitly state `(in Rupees (Excl of GST))`. If cross-border work orders are introduced in foreign currencies in the future, a currency conversion service will be required.
