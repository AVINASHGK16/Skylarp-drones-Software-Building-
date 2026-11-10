# Phase 3.1: Deal Classification and KPI Reconciliation

**Auditor:** Senior Backend Engineer & Quantitative Systems Auditor  
**Date:** November 9, 2026  
**Dataset:** Monday.com / Local Excel Backup (`Deal funnel Data.xlsx`)  
**Mode:** READ-ONLY Verification and Mathematical Reconciliation  

---

## 1. Executive Summary

This report delivers an independent, empirical reconciliation of all **346 records** in the deals dataset. Every deal was audited across its raw and cleaned states to establish a **mutually exclusive, collectively exhaustive (MECE)** classification taxonomy, reconcile every quantitative claim from the previous audit, and diagnose status/stage semantic conflicts.

### Key Conclusions:
1. **The 346 Records Reconcile Perfectly:**
   - 165 Won deals ($₹9.50\text{ Cr}$)
   - 42 Lost deals ($₹98.25\text{ Cr}$)
   - 85 Dead or Abandoned deals ($₹53.98\text{ Cr}$)
   - 52 Open / Active deals ($₹68.82\text{ Cr}$)
   - 2 Header row artifacts ($₹0.00$)
   - **Total Deal Count:** $165 + 42 + 85 + 52 + 2 = \mathbf{346\text{ deals}}$
   - **Total Pipeline Sum:** $\mathbf{₹230,55,18,040.91}$ ($₹230.55\text{ Crore}$)
2. **Discrepancy Resolutions Confirmed:**
   - **127 vs. 42 vs. 84 vs. 85:** There are 127 deals with `Deal Status == 'Dead'`. 42 have `Deal Stage == 'L. Project Lost'`, leaving **85 Dead deals** with other stages. One of those 85 has `Deal Stage == 'G. Project Won'` (Row 178, value ₹26.91 Lakh). The previous audit identified 84 Dead deals by excluding won stages (`is_won`). In truth, Row 178 was marked Dead after winning (or vice-versa).
   - **52 vs. 53 Active Deals:** There are 49 deals with `Deal Status == 'Open'` ($₹68.82\text{ Cr}$), 2 deals with `Deal Status == 'On Hold'` ($₹0.00$), and 1 deal with `Deal Status == NaN` (Row 47, stage `"A. Lead Generated"`, value $₹0.00$). Together, they form **52 valid active deals**. The 53 figure in initial heuristics counted an extra repeated header row before clean parsing.
3. **Severe Analytics Engine Inversion:**
   The current analytics engine ([`analytics_engine.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py)) calculates active deals residually as `total_deals - (won + lost)`. Because it only searches for `"lost"` or `"won"`, it misclassifies **84 Dead deals** ($₹53.71\text{ Cr}$), **2 On Hold deals**, **1 Unspecified deal**, and **2 Header artifacts** as active, reporting **138 active deals** worth **₹122.52 Crore** instead of **52 active deals** worth **₹68.82 Crore**.

---

## 2. Mutually Exclusive Deal Classification Taxonomy

To ensure zero overlap and zero omitted records, the application must classify deals into the following six standardized categories:

1. **`WON`**: Deals where commercial engagement concluded with a signed contract, formal award, or executed delivery.
2. **`LOST`**: Deals actively pursued by sales but explicitly lost to competitors, budgetary disqualification, or formal prospect rejection.
3. **`DEAD_OR_ABANDONED`**: Opportunities dropped, deemed irrelevant, abandoned due to unresponsiveness, or placed on indefinite terminal hold.
4. **`CANCELLED`**: Deals formally terminated or annulled after initial engagement (no explicit `"Cancelled"` string exists in the raw status field, but several stages represent this outcome).
5. **`OPEN_ACTIVE`**: Live opportunities progressing through active discovery, proposal, negotiation, or contract drafting.
6. **`UNKNOWN_OR_UNCLASSIFIED`**: Incomplete entries, missing metadata, or ingested file artifacts (e.g. repeated table headers).

### Comprehensive Reconciliation Table

| Classification Category | Deal Count | Total Value (₹) | Total Value (Crore) | % of Total Count | % of Total Value |
|---|---:|---:|---:|---:|---:|
| **WON** | 165 | ₹9,50,38,938.98 | ₹9.50 Cr | 47.69% | 4.12% |
| **LOST** | 42 | ₹98,25,41,075.81 | ₹98.25 Cr | 12.14% | 42.62% |
| **DEAD_OR_ABANDONED** | 85 | ₹53,97,85,732.96 | ₹53.98 Cr | 24.57% | 23.41% |
| **OPEN_ACTIVE** | 52 | ₹68,81,52,293.17 | ₹68.82 Cr | 15.03% | 29.85% |
| **UNKNOWN_OR_UNCLASSIFIED** | 2 | ₹0.00 | ₹0.00 Cr | 0.58% | 0.00% |
| **TOTALS** | **346** | **₹230,55,18,040.91** | **₹230.55 Cr** | **100.00%** | **100.00%** |

*(Note: Sum of values and counts reconciles 100% to the raw and cleaned dataset totals.)*

---

## 3. Detailed Cross-Tabulation and Conflict Audit

### Full Cross-Tabulation: Deal Status vs. Deal Stage

| Deal Status | Lead Gen (A) | SQL (B) | Demo Done (C) | Feasibility (D) | Proposal Sent (E) | Negotiations (F) | Won (G) | WO Recd (H) | POC (I) | Invoice Sent (J) | Accrued (K) | Lost (L) | On Hold (M) | Not Rel Moment (N) | Not Rel All (O) | Completed | Header | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Dead** | 0 | 6 | 6 | 1 | 9 | 0 | **1** | 0 | 3 | 5 | 0 | 42 | 17 | 19 | 18 | 0 | 0 | **127** |
| **Won** | **70** | 0 | 0 | 0 | 0 | 2 | 26 | 45 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 19 | 0 | **165** |
| **Open** | 3 | 8 | 3 | 3 | 19 | 11 | 0 | **1** | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | **49** |
| **On Hold** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | **2** |
| **Unspecified** | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **1** |
| **Deal Status** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | **2** |
| **Total** | **74** | **14** | **9** | **4** | **28** | **13** | **27** | **46** | **3** | **6** | **2** | **42** | **20** | **19** | **18** | **19** | **2** | **346** |

---

### Audit of Conflicting Records & Classification Rules

#### Conflict 1: Row 178 — `Deal Status == 'Dead'` but `Deal Stage == 'G. Project Won'`
- **Record Details:** `Deal Name: 'Bugs Bunny'`, `Client Code: 'COMPANY105'`, `Value: ₹26,91,480.00`.
- **Diagnosis:** The opportunity initially reached `"Project Won"`, but the project subsequently fell through or was abandoned before contract execution, causing the sales rep to mark `Deal Status: 'Dead'`.
- **Classification Rule:** **Status overrides Stage for terminal abandonment.** When `Deal Status == 'Dead'`, the business relationship is deceased. Classified as `DEAD_OR_ABANDONED`.

#### Conflict 2: Rows 180–249 (70 Deals) — `Deal Status == 'Won'` but `Deal Stage == 'A. Lead Generated'`
- **Record Details:** 70 consecutive records from bulk historical uploads (e.g. `Bugs Bunny`, `Scooby-Doo`, `Shaggy`). All 70 rows have `Masked Deal value == NaN` (coerced to ₹0.00).
- **Diagnosis:** Rapid historical entry artifact where past contracted accounts were imported into Monday.com with status `"Won"` without advancing the workflow stage from the default `"Lead Generated"`.
- **Classification Rule:** **Status 'Won' is authoritative for closed business.** Classified as `WON`. Value contributes ₹0.00 to total won revenue but correctly increments won deal count.

#### Conflict 3: Row 10 — `Deal Status == 'Open'` but `Deal Stage == 'H. Work Order Received'`
- **Record Details:** `Deal Name: 'Sakura'`, `Client Code: 'COMPANY149'`, `Value: ₹42,81,900.00`.
- **Diagnosis:** Work order was received from the client, but commercial deal closing paperwork remains in final administrative processing.
- **Classification Rule:** Classified as `OPEN_ACTIVE`. This is high-probability active closing pipeline.

#### Conflict 4: Row 47 — Missing Status (`Deal Status == NaN`)
- **Record Details:** `Deal Name: 'Tanjiro'`, `Deal Stage: 'A. Lead Generated'`, `Value: NaN`.
- **Diagnosis:** Fresh unassigned inbound lead created on `2026-01-08`.
- **Classification Rule:** Unspecified status with an open lead stage is classified as `OPEN_ACTIVE` (active top-of-funnel discovery).

#### Conflict 5: Rows 50 and 179 — Repeated Column Headers
- **Record Details:** `Deal Status == 'Deal Status'`, `Deal Stage == 'Deal Stage'`.
- **Diagnosis:** Direct ingestion of concatenated CSV/Excel header lines.
- **Classification Rule:** Classified as `UNKNOWN_OR_UNCLASSIFIED` and must be filtered out of all KPI metrics.

---

## 4. Verification and Reconciliation of Previous Audit Claims

The previous audit's assertions were verified through direct execution against the source dataset:

| Claimed Metric | Previous Audit Claim | Independent Verification | Exact Source Condition / Formula | Status |
|---|---|---|---|---|
| **Total Deals** | 346 | **346** | `len(df_deals)` | **CONFIRMED** |
| **Won Deals** | 166 | **165 (Status) / 166 (Heuristic)** | `Deal Status == 'Won'` is 165. The engine used `status.str.contains('won') \| stage.str.contains('won')`, which captured Row 178 (`Dead` + `Won stage`), yielding $165 + 1 = 166$. | **RESOLVED** |
| **Dead Deals** | 127 | **127** | `(df['Deal Status'] == 'Dead').sum()` | **CONFIRMED** |
| **Project Lost Stage** | 42 | **42** | `(df['Deal Stage'] == 'L. Project Lost').sum()`. Every one of these 42 rows has `Deal Status == 'Dead'`. | **CONFIRMED** |
| **Misclassified Dead Deals** | 84 | **85 (Total Dead non-lost) / 84 (Active in Engine)** | Total Dead deals with stage $\neq$ Lost is 85. Because Row 178 was counted as Won, the engine left $85 - 1 = 84$ Dead deals in `active_deals`. | **RESOLVED** |
| **Misclassified Dead Value** | ₹53.71 Cr | **₹53,70,94,252.96** | Sum of 84 Dead deals not captured by won/lost heuristic. If Row 178 (₹26.91 L) is included, sum is ₹53.98 Cr. | **CONFIRMED** |
| **Gross Pipeline Value** | ₹230.55 Cr | **₹230,55,18,040.91** | Sum of all deal values across all 346 rows in `df_clean['Masked Deal value']`. | **CONFIRMED** |
| **Lost Deals Value** | ₹98.25 Cr | **₹98,25,41,075.81** | Sum of 42 deals with `Deal Stage == 'L. Project Lost'`. | **CONFIRMED** |
| **Won Deals Value** | ₹9.77 Cr | **₹9,50,38,938.98 (Status) / ₹9,77,30,418.98 (Engine)** | Deals with `Deal Status == 'Won'` total ₹9.50 Cr. The engine added Row 178 (₹26.91 L), producing ₹9.77 Cr. | **RESOLVED** |
| **Active Pipeline Value** | ₹68.82 Cr | **₹68,81,52,293.17** | Sum of all deals with `Deal Status == 'Open'`. | **CONFIRMED** |
| **Active Deal Count** | 52 | **52 (True Active) vs. 49 (Open only)** | 49 Open + 2 On Hold + 1 Unspecified Lead = **52 deals**. | **CONFIRMED** |

---

## 5. Precise KPI Definitions and Mathematical Formulas

### 5.1 Gross Historical Opportunity Value
- **Definition:** The cumulative financial volume of all business opportunities ever entered into the system, regardless of outcome.
- **Formula:**
  $$\text{Gross Opportunity Value} = \sum_{i \in \text{All Valid Deals}} \text{Value}_i$$
- **Dataset Value:** **₹230,55,18,040.91** ($₹230.55\text{ Crore}$) across 344 genuine deals.

### 5.2 Active Pipeline Value (The Executive Metric)
- **Definition:** The total estimated monetary value of open, unclosed deals currently in the sales funnel. Excludes all terminal states (Won, Lost, Dead, Cancelled) and unpursued holds.
- **Formula:**
  $$\text{Active Pipeline Value} = \sum_{i \in \text{OPEN\_ACTIVE}} \text{Value}_i$$
- **Dataset Value:** **₹68,81,52,293.17** ($₹68.82\text{ Crore}$).

### 5.3 Active Deal Count
- **Definition:** The number of opportunities currently undergoing active commercial engagement.
- **Formula:**
  $$\text{Active Deal Count} = N(\text{OPEN\_ACTIVE})$$
- **Dataset Value:** **52 deals** (49 Open + 2 On Hold + 1 Unassigned Inbound Lead).

### 5.4 Won Deal Value & Count
- **Definition:** Financial volume and count of deals successfully converted to contracted accounts.
- **Formula:**
  $$\text{Won Value} = \sum_{i \in \text{WON}} \text{Value}_i, \quad \text{Won Count} = N(\text{WON})$$
- **Dataset Value:** **₹9,50,38,938.98** ($₹9.50\text{ Crore}$) across **165 deals**.

### 5.5 Lost Deal Value & Count
- **Definition:** Financial volume and count of actively pursued deals rejected or lost to competitors.
- **Formula:**
  $$\text{Lost Value} = \sum_{i \in \text{LOST}} \text{Value}_i, \quad \text{Lost Count} = N(\text{LOST})$$
- **Dataset Value:** **₹98,25,41,075.81** ($₹98.25\text{ Crore}$) across **42 deals**.

### 5.6 Dead / Abandoned Deal Value & Count
- **Definition:** Financial volume and count of opportunities that dissolved due to disinterest, qualification failure, or abandonment.
- **Formula:**
  $$\text{Dead Value} = \sum_{i \in \text{DEAD\_OR\_ABANDONED}} \text{Value}_i, \quad \text{Dead Count} = N(\text{DEAD\_OR\_ABANDONED})$$
- **Dataset Value:** **₹53,97,85,732.96** ($₹53.98\text{ Crore}$) across **85 deals**.

### 5.7 Win Rate vs. Closed Conversion Rate
To prevent misleading founder metrics, two distinct rates must be reported:

1. **Terminal Win Rate (Among All Closed/Concluded Engagements):**
   $$\text{Win Rate}_{\text{closed}} = \frac{N(\text{WON})}{N(\text{WON}) + N(\text{LOST}) + N(\text{DEAD})} \times 100$$
   $$\text{Win Rate}_{\text{closed}} = \frac{165}{165 + 42 + 85} \times 100 = \frac{165}{292} \times 100 = \mathbf{56.51\%}$$
   *(If Row 178 is kept in Won: $\frac{166}{292} = \mathbf{56.85\%}$.)*
   *(Current engine reports an inflated **79.81%** by excluding the 85 Dead deals).*

2. **Gross Conversion Rate (Among All Recorded Leads):**
   $$\text{Gross Conversion Rate} = \frac{N(\text{WON})}{N(\text{Valid Total Deals})} \times 100 = \frac{165}{344} \times 100 = \mathbf{47.97\%}$$

3. **Competitive Win Rate (Excluding Passive Dead Leads, Won vs. Explicit Lost Only):**
   $$\text{Competitive Win Rate} = \frac{N(\text{WON})}{N(\text{WON}) + N(\text{LOST})} \times 100 = \frac{165}{165 + 42} \times 100 = \mathbf{79.71\%}$$
   > [!IMPORTANT]
   > The current 79.81% is **not** a general pipeline conversion rate; it is strictly a **Competitive Decision Win Rate** (won vs. formally lost). Labelling it as "Pipeline Conversion Rate" without caveat is a major business intelligence error.

---

## 6. Numeric Parsing Verification

Independent evaluation of [`_clean_numeric_series()`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py#L87-L125) on financial strings:

| Input String | Actual Parser Output | Expected Business Value | Error Factor | Defect Analysis |
|---|---|---|---|---|
| `"₹5,00,000"` | `500000.0` | `500000.0` | $1\times$ (Correct) | Regex matches digits with commas correctly. |
| `"-₹250"` | `-250.0` | `-250.0` | $1\times$ (Correct) | Negative prefix detected correctly. |
| `"(1000)"` | `-1000.0` | `-1000.0` | $1\times$ (Correct) | Accounting parentheses detected correctly. |
| `""` / `"   "` / `None` | `0.0` | `0.0` | $1\times$ (Correct) | Null-safe fallback. |
| `"invalid"` | `0.0` | `0.0` | $1\times$ (Correct) | Regex search failure defaults to `fill_value`. |
| `"5 Lakh"` | **`5.0`** | `500000.0` | **$100,000\times$ undercount** | Discards text unit `"Lakh"`, captures only `"5"`. |
| `"1.5 Crore"` | **`1.5`** | `15000000.0` | **$10,000,000\times$ undercount** | Discards text unit `"Crore"`, captures only `"1.5"`. |
| `"2.5 Cr"` | **`2.5`** | `25000000.0` | **$10,000,000\times$ undercount** | Discards `"Cr"`. |
| `"100K"` | **`100.0`** | `100000.0` | **$1,000\times$ undercount** | Discards `"K"`. |
| `"1.2M"` | **`1.2`** | `1200000.0` | **$1,000,000\times$ undercount** | Discards `"M"`. |

---

## 7. Recommended Implementation Rules for Phase 3.2

When implementing fixes in [`data_cleaner.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py) and [`analytics_engine.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py):

### Rule 1: Header Row Purging in `clean_deals_data`
Filter out table headers before type conversion:
```python
clean_df = clean_df[clean_df["Deal Status"].str.lower() != "deal status"]
```

### Rule 2: Multi-Unit Numeric Normalization in `_clean_numeric_series`
Preserve numbers while evaluating unit multipliers:
```python
multipliers = {
    'crore': 1e7, 'cr': 1e7,
    'lakh': 1e5, 'lac': 1e5,
    'million': 1e6, 'm': 1e6,
    'thousand': 1e3, 'k': 1e3,
}
```

### Rule 3: Deterministic Deal Classification in `get_pipeline_summary`
Replace residual subtraction with positive boolean masking:
```python
status_clean = df["Deal Status"].str.lower()
stage_clean = df["Deal Stage"].str.lower()

# 1. Won
is_won = (status_clean == "won") & (status_clean != "dead")

# 2. Lost
is_lost = (stage_clean == "l. project lost") & (status_clean != "won")

# 3. Dead / Abandoned
is_dead = (status_clean == "dead") & (~is_lost)

# 4. Active Pipeline
is_active = status_clean.isin(["open", "on hold"]) | (status_clean == "unspecified")
```

### Rule 4: Explicit Schema Disaggregation
Expose separate keys in `PipelineSummary`:
- `active_pipeline_value`: ₹68.82 Cr
- `gross_historical_pipeline`: ₹230.55 Cr
- `active_deals`: 52
- `deals_won`: 165
- `deals_lost`: 42
- `deals_dead`: 85
- `closed_win_rate`: 56.51%
- `competitive_win_rate`: 79.71%

