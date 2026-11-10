# Phase 3.2.3 — Source Contract, Missing-Value, and Currency Audit

**Status:** Complete  
**Date:** 2026-11-09  
**Audit Type:** Read-Only Source Contract & Numeric Pipeline Verification  
**Scope:** `backend/services/data_cleaner.py`, `backend/services/analytics_engine.py`, `Deal funnel Data.xlsx`

---

## Executive Summary

This audit independently investigates the source contracts, numeric coercion pipelines, and currency assumptions across the Monday.com / Excel BI pipeline.

1. **Cleaned Dataset Contract (344 vs 346 Rows):**
   `clean_deals_data()` returns **346 rows**, retaining the two repeated header row artifacts (rows 50 and 179) with `Classification = "UNKNOWN_OR_UNCLASSIFIED"` and `Classification Reason = "Repeated table header row artifact"`. They are **not physically removed** during cleaning. Downstream in `analytics_engine.py:get_pipeline_summary()`, they are filtered out via boolean masking (`~is_header_artifact`), leaving exactly **344 valid business deals** in KPI aggregations.

2. **Missing vs. Invalid vs. Zero Information Loss:**
   `_clean_numeric_series()` coerces `None`, `NaN`, `""`, and non-numeric strings (e.g. `"invalid"`, `"TBD"`) to `fill_value=0.0`. Valid zero (`0` or `"0"`) also becomes `0.0`. Consequently, **the cleaned DataFrame cannot distinguish between a missing value, an invalid string, and a genuine zero-value contract**. `get_pipeline_summary()` relies on `numeric_vals == 0.0` to detect missing values, mistakenly classifying genuine ₹0 deals as missing.

3. **Currency Ingestion Assumptions:**
   Raw Excel cells contain unformatted numeric floats/integers with `General` cell formats. Column headers in Work Orders explicitly state `(in Rupees (Excl of GST))`. The numeric cleaner blindly strips `₹`, `rs.`, `inr`, and `$` without currency conversion. As a result, a `$100,000` deal would be parsed as `100000.0` (treated 1:1 as INR, an ~83x understatement), while currencies like `€` (Euro) or `£` (Pound) fail regex matching and are coerced to `0.0`.

---

## 1. Cleaned Dataset Contract Verification

### 1.1 Source Code Excerpts

#### `clean_deals_data()` in [`backend/services/data_cleaner.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py#L365-L380):
```python
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
```
`clean_deals_data()` applies no row drop (`df.drop` or `df.dropna` is not called). Every input row from the raw dataset is preserved in the returned DataFrame.

#### `classify_deal()` in [`backend/services/data_cleaner.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py#L255-L258):
```python
# Rule 6: Header row artifact
if status_lower in ["deal status"] or stage_lower in ["deal stage"]:
    return "UNKNOWN_OR_UNCLASSIFIED", "Repeated table header row artifact"
```

#### `get_pipeline_summary()` in [`backend/services/analytics_engine.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L131-L133):
```python
# Exclude repeated table header artifacts from valid business opportunity volume
is_header_artifact = cat_series == "UNKNOWN_OR_UNCLASSIFIED"
valid_deals_df = df[~is_header_artifact]
```

#### `generate_data_quality_report()` in [`backend/services/data_cleaner.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py#L536-L557):
```python
if deals_count > 0 and "Classification" in deals_df.columns:
    classification_counts = deals_df["Classification"].value_counts().to_dict()
    classification_breakdown = {str(k): int(v) for k, v in classification_counts.items()}
    rejected_header_rows = int((deals_df["Classification"] == "UNKNOWN_OR_UNCLASSIFIED").sum())

report = {
    "total_records": total_records,
    "deals_count": deals_count,
    "work_orders_count": wo_count,
    ...
    "deals_rejected_header_rows": rejected_header_rows,
    "deals_conflicting_records_count": conflicting_records_count,
    "deals_classification_breakdown": classification_breakdown,
}
```

### 1.2 Runtime Output & Reconciliation Table

| Metric / Stage | Row Count | Status | Notes |
|---|---:|---|---|
| Raw Deals Ingestion | 346 | Raw records | Includes rows 50 and 179 from Excel |
| `clean_deals_data()` output | **346** | Preserved | Row 50 and 179 classified as `UNKNOWN_OR_UNCLASSIFIED` |
| `generate_data_quality_report()` | **346** | Ingestion Total | Explicitly reports `deals_rejected_header_rows: 2` |
| `get_pipeline_summary()` valid set | **344** | Analyzed Deals | Excludes rows with `cat_series == "UNKNOWN_OR_UNCLASSIFIED"` |
| `value_coverage["total_records"]` | **344** | Tracked Opportunities | Matches `len(valid_deals_df)` |

**Reconciliation of Phase 3.2 Report Discrepancy:**  
The Phase 3.2 report referred to "344 cleaned deals" in business terms because the two repeated header rows are rejected from all pipeline KPIs and conversion calculations. However, at the DataFrame/data-loader level, `clean_deals_data()` purposefully returns **346 rows** so that row-level index parity with raw input and full auditability are preserved without silent dropping.

---

## 2. Missing and Invalid-Value Preservation Trace

### 2.1 Trace Table Across the Pipeline

We traced 8 representative values through the numeric cleaning and analytics aggregation stages:

| Input Case | Raw Input Value | Type at Ingestion | Cleaned DF Value (`_clean_numeric_series`) | Cleaned DF dtype | Value Coverage Bucket (`get_pipeline_summary`) | Included in Sum? |
|---|---|---|---|---|---|---|
| **Case 1** | `None` | `NoneType` | `0.0` | `float64` | `missing_value_count` | ₹0.00 |
| **Case 2** | `NaN` (float) | `float` | `0.0` | `float64` | `missing_value_count` | ₹0.00 |
| **Case 3** | `""` (empty str) | `str` | `0.0` | `float64` | `missing_value_count` | ₹0.00 |
| **Case 4** | `"invalid string"` | `str` | `0.0` | `float64` | `missing_value_count` | ₹0.00 |
| **Case 5** | `"0"` (string zero) | `str` | `0.0` | `float64` | `missing_value_count` | ₹0.00 |
| **Case 6** | `0` (int zero) | `int` | `0.0` | `float64` | `missing_value_count` | ₹0.00 |
| **Case 7** | `-1000` | `int` | `-1000.0` | `float64` | `valid_numeric_count` | -₹1,000.00 |
| **Case 8** | `"₹5,00,000"` | `str` | `500000.0` | `float64` | `valid_numeric_count` | ₹5,00,000.00 |

### 2.2 Critical Findings on Value Preservation

1. **Information Loss at Cleaning Stage:**  
   In `backend/services/data_cleaner.py:127-169`, `_clean_numeric_series` uses `fill_value=0.0` for all missing and unparseable values:
   ```python
   def _parse_val(val: Any) -> float:
       if pd.isna(val) or val is None:
           return fill_value
       ...
       if not s_val:
           return fill_value
       ...
       # If it doesn't match a recognized number or number+suffix, it is invalid
       return fill_value
   ```
   Once passed through `clean_deals_data()`, **missing values, invalid strings, and genuine zeros are identical (`0.0`)**.

2. **Flawed Value Coverage Logic in Analytics Engine:**  
   In `backend/services/analytics_engine.py:166-177`:
   ```python
   missing_mask = numeric_vals == 0.0
   valid_numeric_count = int((~missing_mask & ~is_header_artifact).sum())
   missing_value_count = int((missing_mask & ~is_header_artifact).sum())

   value_coverage = {
       "total_records": int(len(valid_deals_df)),
       "valid_numeric_count": valid_numeric_count,
       "missing_value_count": missing_value_count,
       "invalid_value_count": 0,
       "sum_valid_values": round(gross_opportunity_val, 2),
   }
   ```
   - **Invalid count is hardcoded to 0** because invalid strings were already collapsed to `0.0` upstream.
   - **Genuine 0 values are counted as missing**: If a deal is legitimately valued at ₹0 (e.g. proof-of-concept, partnership, warranty), it is incorrectly flagged as missing in `missing_value_count`.

---

## 3. Currency Assumptions and Foreign Currency Risk

### 3.1 Raw Excel Cell Formats & Metadata
- **File:** `Deal funnel Data.xlsx`, sheets `Deals` and `Work Orders`.
- **Inspected Cells:** Deal values are stored as raw floating-point numbers or integers (e.g. `200000.0`).
- **Cell Number Format:** `General` (no Excel currency formatting codes like `[$₹-4009]` or `[$$-409]`).
- **Header Naming:**
  - Deals Sheet: `Masked Deal value` (does not declare currency in title).
  - Work Orders Sheet: `Work Order Value (in Rupees (Excl of GST))` (explicitly declares INR).

### 3.2 Parser Behavior on Currencies

In `backend/services/data_cleaner.py:141`:
```python
s_clean = re.sub(r"^(?:rs\.?|inr|usd|\$|₹)\s*", "", s_lower)
s_clean = (
    s_clean.replace(",", "")
    .replace("₹", "")
    .replace("$", "")
    .replace("(", "")
    .replace(")", "")
    .replace("-", "")
    .strip()
)
```

Runtime test results:
- `₹1000` $\rightarrow$ `1000.0`
- `$1000` $\rightarrow$ `1000.0` (Strips `$` and treats as 1000 INR)
- `€1000` $\rightarrow$ `0.0` (Fails regex, treated as invalid string, coerced to 0.0)
- `£1000` $\rightarrow$ `0.0` (Fails regex, treated as invalid string, coerced to 0.0)
- `1000` (unmarked) $\rightarrow$ `1000.0` (Implicitly treated as INR)

### 3.3 Foreign Currency Risks
1. **Blind Stripping of Dollar Signs:**
   Stripping `$` and `usd` without an exchange rate conversion creates a severe financial calculation error. A deal for `$100,000` is parsed as `100,000` in the same column as `₹100,000`, understating its value by a factor of ~83x (assuming 1 USD $\approx$ 83 INR).
2. **Rejection of Non-USD/INR Currencies:**
   European (`€`) or UK (`£`) currencies are discarded as `0.0` rather than being either converted or flagged with a validation warning.
3. **Implicit System-Wide Currency Assumption:**
   The entire BI agent assumes INR throughout its prompt templates, KPI labels, and analytics engine without explicit currency validation at ingestion.

---

## 4. Identified Defects and Recommendations for Phase 3.3

1. **Retain Nullable Numeric Types (`pd.Float64Dtype`):**
   Modify `_clean_numeric_series()` to return `np.nan` (or pandas nullable `Float64`) for missing and invalid entries instead of forcing `0.0`. Store an auxiliary column `Masked Deal value_validity` (`VALID`, `MISSING`, `INVALID`) so that:
   - Genuine ₹0 values have value `0.0` and validity `VALID`.
   - Missing cells have value `NaN` and validity `MISSING`.
   - Malformed strings have value `NaN` and validity `INVALID`.
2. **Proper Value Coverage Calculation:**
   Compute `value_coverage` based on validity flags rather than `numeric_vals == 0.0`.
3. **Explicit Currency Handling:**
   Refuse to blindly strip `$` without exchange rate conversion, or flag records with foreign currency markers as `INVALID_CURRENCY` during ingestion.
