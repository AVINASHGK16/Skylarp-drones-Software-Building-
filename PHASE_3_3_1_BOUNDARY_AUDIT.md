# Phase 3.3.1 — Numeric Integrity and API Boundary Verification Audit (READ-ONLY)

**Status:** Complete  
**Date:** 2026-11-09  
**Audit Type:** Read-Only Verification of Currency Coverage, API Serialization, and Analytics Aggregations  
**Scope:** `backend/services/data_cleaner.py`, `backend/services/analytics_engine.py`, `backend/api/routes.py`, `backend/main.py`, `backend/verify_pipeline.py`

---

## 1. Executive Summary

This independent audit verifies the numeric integrity remediation implemented in Phase 3.3 across currency coverage, API response serialization, analytics aggregation functions, negative-value semantics, and source-currency contracts.

Key findings:
1. **Unsupported Currency Coverage:** Foreign currencies (`USD`, `$`, `EUR`, `€`) are cleanly intercepted by `parse_numeric_value()` with `status = "UNSUPPORTED_CURRENCY"`, `value = None`. In `get_pipeline_summary()`, they are counted under `invalid_value_count`, strictly satisfying the invariant:
   $$\text{valid\_numeric\_count} + \text{missing\_value\_count} + \text{invalid\_value\_count} == \text{total\_records}$$
   No foreign currency enters INR sums. In diagnostics, `data_quality_report` tracks `deals_unsupported_currency_values` distinctly.
2. **API Serialization Integrity:** Verified across `/health`, `/ready`, `/data-status`, `/metrics`, `/ask`, and `/leadership-report`. All responses are strictly RFC 8259 compliant. Zero non-standard tokens (`NaN`, `Infinity`, `-Infinity`) escape into responses. Missing values correctly serialize as JSON `null`.
3. **Analytics Aggregations:** All four deal aggregation functions (`get_pipeline_summary`, `get_revenue_by_sector`, `get_revenue_by_stage`, `get_monthly_pipeline`) strictly exclude repeated header artifacts (`UNKNOWN_OR_UNCLASSIFIED`) and restrict sums to `status == "VALID"`. Regional and deal-size aggregations are not implemented in the backend.
4. **Negative-Value Semantics:** Negative deal values are treated as algebraic credits/deductions to the pipeline total and are factored into the average deal value denominator.
5. **Currency Source Contract:** `Deal funnel Data.xlsx` does not explicitly declare `INR` or `Rupees` in its headers or cell metadata; this remains an inferred domain assumption derived from the sister workbook (`Work_Order_Tracker Data.xlsx`).
6. **Verification Output Defect:** `analytics_engine.py` (lines 245 and 490) continues to use `$` formatting strings in logger statements (`$%.2f gross opportunity`, `$%.2f billed`), producing misleading dollar symbols in `verify_pipeline.py` console logs despite values being INR.

---

## 2. Unsupported Currency Coverage Verification

### 2.1 Synthetic Dataset Test

A synthetic dataset was tested against `clean_deals_data()` and `get_pipeline_summary()`:
- 1 valid INR value: `"₹50,000"`
- 1 valid zero: `"0"`
- 1 missing value: `None`
- 1 invalid string: `"invalid text"`
- 1 explicit USD value: `"$1000"`
- 1 explicit EUR value: `"€500"`

### 2.2 Results and Metric Output

```json
{
  "gross_historical_opportunity_value": 50000.0,
  "active_pipeline_value": 50000.0,
  "open_deal_count": 6,
  "value_coverage": {
    "total_records": 6,
    "valid_numeric_count": 2,
    "missing_value_count": 1,
    "invalid_value_count": 3,
    "sum_valid_values": 50000.0
  },
  "average_deal_value": 25000.0
}
```

### 2.3 Row-by-Row Trace

| Record | Raw Value | Status (`_status`) | Parsed Value | Reason (`_reason`) | Coverage Bucket | Included in Sum? |
|---|---|---|---|---|---|---|
| Deal 1 | `"₹50,000"` | `VALID` | `50000.0` | Parsed plain numeric string | `valid_numeric_count` | Yes (₹50,000.00) |
| Deal 2 | `"0"` | `VALID` | `0.0` | Parsed plain numeric string | `valid_numeric_count` | Yes (₹0.00) |
| Deal 3 | `None` | `MISSING` | `NaN` / `None` | Missing value (None or NaN) | `missing_value_count` | Excluded |
| Deal 4 | `"invalid text"` | `INVALID` | `NaN` / `None` | Unrecognized numeric format | `invalid_value_count` | Excluded |
| Deal 5 | `"$1000"` | `UNSUPPORTED_CURRENCY` | `NaN` / `None` | Unsupported foreign currency [USD] | `invalid_value_count` | Excluded |
| Deal 6 | `"€500"` | `UNSUPPORTED_CURRENCY` | `NaN` / `None` | Unsupported foreign currency [EUR] | `invalid_value_count` | Excluded |

### 2.4 Invariant Verification
- **Total records:** 6
- **Valid records:** 2 (INR Deal + Zero Deal)
- **Missing records:** 1
- **Invalid records:** 3 (1 unparseable text + 2 unsupported foreign currencies)
$$\text{valid\_numeric\_count} (2) + \text{missing\_value\_count} (1) + \text{invalid\_value\_count} (3) == \text{total\_records} (6)$$
- **Total sum:** ₹50,000.00. Neither USD ($1,000) nor EUR (€500) entered the INR total.
- **Diagnostics:** `generate_data_quality_report` reported:
  - `deals_missing_financial_values: 1`
  - `deals_invalid_financial_values: 1`
  - `deals_unsupported_currency_values: 2`

---

## 3. API Serialization Verification

All API endpoints were traced using the FastAPI `TestClient` with full startup lifespan execution:

| Endpoint | Method | HTTP Status | Non-Standard Tokens (`NaN`/`Infinity`)? | RFC 8259 Compliant? | Missing Values Serialization |
|---|---|---:|---|---|---|
| `/health` | `GET` | 200 OK | None | Compliant | N/A |
| `/ready` | `GET` | 200 OK | None | Compliant | `fallback_reason: null` |
| `/data-status` | `GET` | 200 OK | None | Compliant | `data_as_of: null` |
| `/metrics` | `GET` | 200 OK | None | Compliant | `formal_decision_win_rate: null` (if 0 denom) |
| `/ask` | `POST` | 200 OK | None | Compliant | Metrics serialized cleanly |
| `/leadership-report` | `GET` | 200 OK | None | Compliant | Markdown string payload |

### Key Findings
1. **RFC 8259 JSON Standard Adherence:** Tested using Python `json.loads(text, parse_constant=forbid_nan)` where any occurrence of `NaN`, `Infinity`, or `-Infinity` triggers an immediate fatal exception. All endpoints passed with `RFC 8259 Compliant JSON: TRUE`.
2. **Missing Floating-Point Values:** In `analytics_engine.py`, missing rates (such as win rates when denominator is 0) return `None`, which serialize as valid JSON `null`.
3. **No NumPy Serialization Failures:** All numeric outputs are explicitly cast to native Python `float`, `int`, or rounded via `round(float(...), 2)` before inclusion in returned dictionaries.

---

## 4. Comprehensive Audit of Analytics Aggregations

Every public and private aggregation function in `backend/services/analytics_engine.py` was audited:

| Function | Consumes | Header Artifacts Excluded? | Missing & Invalid Excluded from Sums? | Valid Zero Handled? | Negative Values Handled? | Denominator Defensibility |
|---|---|---|---|---|---|---|
| `get_pipeline_summary()` | Deals | **Yes** (`~is_header_artifact`) | **Yes** (`is_valid_value`) | **Yes** (adds 0 to sum, +1 count) | **Yes** (algebraic reduction) | **Defensible:** Denominator for `average_deal_value` includes only open deals with valid values ($N=47$ on real data). |
| `get_revenue_by_sector()` | Deals | **Yes** (`df["Classification"] != "UNKNOWN..."`) | **Yes** (masked with `status == "VALID"`) | **Yes** (contributes 0.0) | **Yes** (algebraic reduction) | N/A (Grouped sum by sector). |
| `get_revenue_by_stage()` | Deals | **Yes** (`df["Classification"] != "UNKNOWN..."`) | **Yes** (masked with `status == "VALID"`) | **Yes** (contributes 0.0) | **Yes** (algebraic reduction) | N/A (Grouped sum by stage). |
| `get_monthly_pipeline()` | Deals | **Yes** (`df["Classification"] != "UNKNOWN..."`) | **Yes** (masked with `status == "VALID"`) | **Yes** (contributes 0.0) | **Yes** (algebraic reduction) | N/A (Grouped sum by month `YYYY-MM`). Missing dates dropped. |
| `get_work_order_summary()` | Work Orders | N/A | N/A | N/A | N/A | `total_wo` is total work orders ($N=176$). |
| `get_billing_summary()` | Work Orders | N/A | Coerced to 0.0 via `_safe_numeric_series` | **Yes** (contributes 0.0) | **Yes** (algebraic reduction) | `billing_percentage` = `total_billed / total_contract`. |
| `get_top_customers()` | Work Orders | N/A | Coerced to 0.0 via `_safe_numeric_series` | **Yes** | **Yes** | N/A (Sorted sum head(10)). |
| `get_execution_metrics()` | Work Orders | N/A | Missing coerced to 0.0 | **Yes** | **Yes** | **Diluted Denominator:** `average_project_value` divides by `total_projects` (176) after filling missing values with `0.0`. |
| *Revenue by Region* | Deals | **Not Implemented** | N/A | N/A | N/A | No regional field or aggregation exists. |
| *Revenue by Deal Size* | Deals | **Not Implemented** | N/A | N/A | N/A | No deal size categorization function exists. |

---

## 5. Negative-Value Semantics

### 5.1 Test Execution on Synthetic OPEN Deals

Tested 5 synthetic OPEN deals:
1. Positive Deal: ₹100,000
2. Zero Deal: ₹0
3. Negative Deal: -₹20,000
4. Missing Deal: `None`
5. Invalid Deal: `"TBD"`

### 5.2 Results
```
Total Deals: 5
Active Deals: 5
Active Pipeline Value: ₹80,000.00
Average Deal Value: ₹26,666.67
Value Coverage: {
  'total_records': 5,
  'valid_numeric_count': 3,
  'missing_value_count': 1,
  'invalid_value_count': 1,
  'sum_valid_values': 80000.0
}
```

### 5.3 Semantic Documentation
- **Active Pipeline Sum:** ₹100,000 + ₹0 + (-₹20,000) = **₹80,000.00**.
- **Average Deal Value:** ₹80,000.00 / 3 = **₹26,666.67**.
- **Business Interpretation:**
  - Negative values currently act as **algebraic credits or downward contract adjustments**.
  - They reduce both the pipeline sum and the mean deal size.
  - The denominator includes all 3 valid records (`Positive`, `Zero`, `Negative`) and strictly excludes `Missing` and `Invalid`.
  - **Risk:** If negative entries in raw data represent accidental data-entry typos (e.g. typing `-50000` instead of `50000`) rather than genuine credit memos, they will silently deflate revenue pipeline figures.

---

## 6. Currency Source Contract Findings

An inspection of the repository files revealed:
1. **`Deal funnel Data.xlsx`:** The column header is `Masked Deal value`. Cell formats are `General` without currency formatting (`[$₹-4009]`). There is **no explicit statement** in the Deals sheet defining the currency as INR.
2. **`Work_Order_Tracker Data.xlsx`:** The column headers explicitly state:
   - `Amount in Rupees (Excl of GST) (Masked)`
   - `Billed Value in Rupees (Excl of GST.) (Masked)`
3. **Environment & Configuration:** `.env` and `.env.example` declare API keys and model parameters, but contain no `DEFAULT_CURRENCY` setting.
4. **Conclusion:** Unmarked numbers in Deals are **inferred** to be INR based on Skylarp Drones' operational location (India) and the sister Work Orders sheet. This is an **unresolved domain assumption**, not an authoritative contract within the Deals data source itself.

---

## 7. Verification Output & Logging Defects

An inspection of `backend/verify_pipeline.py` and its underlying log emissions identified:
- **Misleading Currency Labels in Logger Strings:**
  - In `backend/services/analytics_engine.py:245`:
    ```python
    logger.info("Pipeline summary calculated: %d total valid deals, $%.2f gross opportunity, $%.2f active pipeline.", ...)
    ```
  - In `backend/services/analytics_engine.py:490`:
    ```python
    logger.info("Billing summary calculated: $%.2f billed out of $%.2f total contract.", ...)
    ```
- **Observed Console Output in `verify_pipeline.py`:**
  ```text
  Pipeline summary calculated: 344 total valid deals, $2305518040.91 gross opportunity, $688152293.17 active pipeline.
  Billing summary calculated: $107389776.59 billed out of $211649409.21 total contract.
  ```
- **Defect:** Despite all calculations being INR-denominated, the log format strings still use hardcoded `$` signs. Under the read-only mandate of Phase 3.3.1, this was not modified and is flagged for remediation.

---

## 8. Summary of Identified Defects & Remediation Plan

| Item | Category | Severity | Description | Recommended Remediation |
|---|---|---|---|---|
| 1 | Logging / Display | Low | `analytics_engine.py:245, 490` hardcode `$` in log formatting strings. | Replace `$` with `₹` or `INR` in log templates. |
| 2 | Analytics / Work Orders | Medium | `get_execution_metrics()` dilutes `average_project_value` by dividing by `total_projects` (176) after zero-filling missing values. | Compute mean across only work orders with valid non-missing contract values. |
| 3 | Data Contract | Low | Source currency is inferred from Work Orders rather than explicitly declared for Deals. | Add `DEFAULT_CURRENCY=INR` in `.env` and document Deals board assumption. |
| 4 | Coverage Breakdown | Minor | `value_coverage` combines general invalid and unsupported currencies into `invalid_value_count`. | Optionally surface `unsupported_currency_count` as a separate key while maintaining the invariant. |
