# Phase 3: BI Analytics and Answer Correctness Audit

**Auditor:** Senior Backend Engineer & Quantitative Systems Auditor  
**Date:** November 9, 2026  
**Target:** Monday.com / Excel Ingestion, Analytics Engine, and Groq BI Agent Context Pipeline  
**Mode:** READ-ONLY Codebase & Data Verification Audit  

---

## 1. Executive Summary

This audit examined the end-to-end mathematical correctness and data integrity of the Monday.com / Excel BI application across three core layers:
1. **Data Cleaning & Normalization** ([`backend/services/data_cleaner.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py))
2. **Deterministic Analytics Engine** ([`backend/services/analytics_engine.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py))
3. **Groq LLM Context Generation & Prompt Orchestration** ([`backend/services/bi_agent.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/bi_agent.py), [`backend/api/routes.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/api/routes.py))

### Key Confirmed Findings:
- **CRITICAL STATUS DEFECT: "Dead" / Cancelled Deals Misclassified as Active Pipeline:** In [`analytics_engine.py:90-100`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L90-L100), active deals are computed residually as `active_deals = total_deals - (deals_won + deals_lost)`. In the actual enterprise dataset, cancelled and lost deals carry the explicit status `"Dead"` (127 deals total). However, the engine only searches for the literal substring `"lost"` or `"won"`. As a result, **84 "Dead" deals totaling ₹53.71 Crore are falsely classified as active opportunities**, severely inflating the active pipeline metrics presented to leadership.
- **CRITICAL KPI MISNOMER: Total Pipeline Value Includes All Historic Won and Lost Deals:** [`get_pipeline_summary()`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L85) sums every non-null deal value in the entire board (totaling ₹230.55 Crore), including ₹98.25 Crore of permanently lost projects and ₹9.77 Crore of won deals. The application does not calculate an active pipeline value KPI.
- **CRITICAL CONVERSION RATE FORMULA INVERSION:** [`analytics_engine.py:102-108`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L102-L108) defines `conversion_rate = (deals_won / (deals_won + deals_lost)) * 100`. Because 84 Dead deals were omitted from `deals_lost`, closed deals are computed as $166 / (166 + 42) = 79.81\%$. When properly computed against all closed/dead deals ($166 / (166 + 127)$), the true win conversion rate is **56.66%** — a 23.15 percentage point exaggeration.
- **NUMERIC PARSING COLLAPSE ON LAKH / CRORE / MILLION UNITS:** [`_clean_numeric_series()`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py#L87-L125) strips letters and extracts the first number sequence. Values entered in standard Indian financial notations (e.g. `"5 Lakh"` or `"1.5 Crore"`) collapse to `5.0` and `1.5` respectively, representing a $100,000\times$ to $10,000,000\times$ undercounting error.
- **HEADER ROW BLEED-THROUGH:** Repeated header rows from concatenated Excel sheets (2 rows having `Deal Status == 'Deal Status'`) are ingested as legitimate deals with value ₹0.0, distorting deal counts and average deal size.
- **GROQ CONTEXT BLIND SPOTS & STATELESS CHAT:** The BI agent receives only pre-aggregated summary dictionaries and top 10 customers. It receives zero row-level deal records, zero client codes, and zero multi-turn conversational history. The frontend displays a chat window, but the backend is completely stateless (`AskRequest` takes only `question: str`).

---

## 2. KPI Definitions and Formulas

| KPI Name | Current Implementation Formula | Intended Business Definition | Assessment |
|---|---|---|---|
| **Total Pipeline Value** | $\sum \text{Deal Value}$ for all records in table | Total value of active open deals (or explicit historic gross deal volume) | **MISLEADING**: Sums active, won, dead, and lost deals together (₹230.55 Cr). |
| **Active Pipeline Value** | **NOT IMPLEMENTED** | $\sum \text{Deal Value}$ for Open / In-Progress deals | **MISSING**: Executives asking for active pipeline receive gross historic pipeline instead. |
| **Active Deals Count** | $N_{\text{total}} - (N_{\text{won}} + N_{\text{lost}})$ | Count of currently open, non-terminal deals | **CONFIRMED DEFECT**: Substring check misses `"Dead"`, classifying 84 dead deals as active. |
| **Deals Won Count** | Substring `"won"` in status or stage | Count of successfully closed/contracted deals | **ACCEPTABLE**: Identifies 166 won deals accurately. |
| **Deals Lost Count** | Substring `"lost"` in status or stage | Count of cancelled, dropped, or lost deals | **CONFIRMED DEFECT**: Captures 42 stage-marked deals; misses 84 `"Dead"` status deals. |
| **Pipeline Conversion Rate** | $\frac{N_{\text{won}}}{N_{\text{won}} + N_{\text{lost}}} \times 100$ | $\frac{N_{\text{won}}}{N_{\text{total closed}}} \times 100$ or $\frac{N_{\text{won}}}{N_{\text{total}}} \times 100$ | **CONFIRMED DEFECT**: Produces 79.81% instead of true 56.66% due to missing Dead deals. |
| **Average Deal Value** | $\frac{\text{Total Pipeline Value}}{N_{\text{total}}}$ | $\frac{\text{Active Pipeline Value}}{N_{\text{active}}}$ or $\frac{\text{Won Value}}{N_{\text{won}}}$ | **DISTORTED**: Blends $0 value rows, lost deals, and repeated header rows into the denominator. |
| **Total Billed Revenue** | $\sum \text{Billed Value in Rupees}$ | Total invoiced and realized work order revenue | **ACCURATE**: ₹10.74 Crore across 176 work orders. |
| **Total Contract Value** | $\sum \text{Amount in Rupees (Excl GST)}$ | Total signed work order contract commitments | **ACCURATE**: ₹21.16 Crore across 176 work orders. |
| **Unbilled Backlog** | $\max(0, \text{Contract Value} - \text{Billed Value})$ | Remaining contract value to be executed and invoiced | **ACCURATE**: ₹10.43 Crore. |
| **Work Order Completion Rate** | $\frac{N_{\text{completed}}}{N_{\text{total WO}}} \times 100$ | Completed projects over total commissioned projects | **ACCURATE**: 67.61% (119 completed out of 176). |

---

## 3. Verified Calculation Paths with File and Line References

### 3.1 Pipeline Summary Calculation
- **Source:** [`backend/services/analytics_engine.py:55-121`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L55-L121)
- **Trace:**
  1. `values = _safe_numeric_series(df, "Masked Deal value")` (line 84).
  2. `total_pipeline_value = float(values.sum())` (line 85) $\rightarrow$ Sums all rows without filtering for status.
  3. `is_won = status_series.str.contains("won", na=False) | stage_series.str.contains("won", na=False)` (line 95).
  4. `is_lost = status_series.str.contains("lost", na=False) | stage_series.str.contains("lost", na=False)` (line 96).
  5. `active_deals = int(total_deals - (deals_won + deals_lost))` (line 100).
- **The Defect:** In `Deal funnel Data.xlsx`, there are 127 rows where `Deal Status == 'Dead'`. Only 42 of those rows have `Deal Stage == 'L. Project Lost'`. The remaining 84 rows have stages such as `"N. Not relevant at the moment"`, `"O. Not Relevant at all"`, or `"M. Projects On Hold"`. Because neither the string `"won"` nor `"lost"` appears, the engine leaves both `is_won` and `is_lost` as `False`, forcing them into `active_deals`.

### 3.2 Revenue by Sector & Deal Stage
- **Source:** [`backend/services/analytics_engine.py:124-182`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L124-L182)
- **Trace:** Groupby operations group across the entire DataFrame without separating active from lost/won deals.
- **Impact:** In `revenue_by_stage`, stage `"L. Project Lost"` is included as the single largest revenue category ($₹98,25,41,075.81$), which accounts for 42.6% of the entire reported pipeline. If leadership views this chart as "future revenue", it creates severe misdirection.

### 3.3 Monthly Pipeline Chronology
- **Source:** [`backend/services/analytics_engine.py:184-227`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L184-L227)
- **Trace:** Effective date resolution fallback:
  ```python
  effective_dates = close_dates.fillna(tentative_dates).fillna(created_dates)
  ```
- **Finding:** In the deals dataset, `Close Date (A)` has only 26 valid values (320 missing). The fallback correctly chains to `Tentative Close Date` and `Created Date`, allowing 19 distinct months to be graphed. However, lost deals from 2024 and 2025 remain in this timeline without visual separation from active pipeline.

### 3.4 Work Order & Billing Summary
- **Source:** [`backend/services/analytics_engine.py:229-340`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py#L229-L340)
- **Trace:**
  - Status categorization uses regex:
    ```python
    is_completed = s_lower.str.contains("completed|done|delivered|closed|finished", regex=True, na=False)
    is_ongoing = s_lower.str.contains("progress|ongoing|active|executing|wip|in-progress", regex=True, na=False)
    is_pending = s_lower.str.contains("pending|upcoming|not started|hold|draft", regex=True, na=False)
    ```
  - Categorizes 119 completed (117 Completed + 2 Partial Completed), 25 ongoing, and 12 executed until current month.
  - Contract total: ₹21.16 Crore; Billed total: ₹10.74 Crore; Unbilled backlog: ₹10.43 Crore.
  - Math is internally consistent and robust against nulls.

---

## 4. Numeric Parsing and Data Quality Audit

[`backend/services/data_cleaner.py:87-125`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py#L87-L125) implements `_clean_numeric_series`:

```python
match = re.search(r"\d+(?:,\d+)*(?:\.\d+)?", s_val)
if match:
    num_str = match.group(0).replace(",", "")
    num_float = float(num_str)
    return -num_float if is_negative else num_float
```

### Verified Parsing Behavior:

| Input String | Actual Parsed Output | Expected Business Meaning | Correctness Status | Risk & Root Cause |
|---|---|---|---|---|
| `"₹5,00,000"` | `500000.0` | ₹5,00,000 | **PASS** | Regex safely strips currency symbols and commas. |
| `"₹ 1,23,456.78"`| `123456.78` | ₹1,23,456.78 | **PASS** | Handles Indian comma grouping with decimals. |
| `"-₹250"` | `-250.0` | -₹250 | **PASS** | Detects leading minus sign. |
| `"(1000)"` | `-1000.0` | -₹1,000 | **PASS** | Detects accounting parentheses as negative. |
| `""` or `"   "` | `0.0` | Missing / zero | **PASS** | Replaced with default `0.0`. |
| `"invalid"` | `0.0` | Missing / zero | **PASS** | Fallback to `0.0`. |
| `"5 Lakh"` | **`5.0`** | ₹5,00,000 | **CRITICAL BUG** | Regex grabs `"5"` and discards `"Lakh"`. Undercounts by $100,000\times$. |
| `"1.5 Crore"` | **`1.5`** | ₹1,50,00,000 | **CRITICAL BUG** | Regex grabs `"1.5"` and discards `"Crore"`. Undercounts by $10,000,000\times$. |
| `"10M"` | **`10.0`** | ₹10,000,000 | **HIGH BUG** | Regex strips `"M"`, reducing 10 Million to 10. |
| `"Deal Status"` | `0.0` | Repeated CSV header | **RISK** | Ingests header string as row with 0.0 value. |

---

## 5. Pipeline Comparisons and Segment Analysis Audit

An audit was conducted on how the system performs comparisons across sectors, timeframes, and customer segments:

1. **Explicit Pipeline Comparison Functions:**
   - **Finding:** NOT FOUND in `analytics_engine.py`. There are no comparative analytical functions (such as Quarter-over-Quarter, Sector vs. Sector variance, or Pipeline Velocity comparisons).
2. **Ad-Hoc LLM Comparisons:**
   - All comparisons are generated dynamically inside the LLM prompt of the BI Agent (`BIAgent.answer_question`).
   - When an executive asks: *"Compare Powerline and Mining performance"*, the Groq model performs mental arithmetic using the static JSON payload in `=== BUSINESS ANALYTICS METRICS CONTEXT ===`.
3. **Risks of Unanchored LLM Comparisons:**
   - **Division by Zero:** If a sector has 0 deals or 0 revenue, the model may fabricate percentage growth figures or hallucinate rates.
   - **Metric Mixing:** The LLM can conflate `Masked Deal value` (sales pipeline) with `Amount in Rupees (Excl of GST)` (executed work orders), comparing pre-sales estimates with operational delivery milestones as if they were identical currencies and pipelines.

---

## 6. Groq BI Agent Context and Hallucination-Risk Audit

The execution path was inspected across [`backend/api/routes.py:160-210`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/api/routes.py#L160-L210) and [`backend/services/bi_agent.py:91-225`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/bi_agent.py#L91-L225).

### 6.1 What the Model Receives
The model receives a single static text block generated by `_build_context()` containing 9 JSON keys:
1. `pipeline_summary` (7 scalar numbers)
2. `revenue_by_sector` (13 key-value pairs)
3. `revenue_by_stage` (17 key-value pairs)
4. `monthly_pipeline` (19 key-value pairs)
5. `work_order_summary` (status counts and completion rate)
6. `billing_summary` (contract, billed, unbilled, percentage)
7. `top_customers` (List of top 10 customer codes with billed revenue)
8. `execution_metrics` (average project value, dates delivery counts)
9. `caveats` (list of data quality warning strings)

### 6.2 What the Model Does NOT Receive
- **Zero Raw Deal Records:** The model does not see individual deal names, owners, client codes, creation dates, or probability ratings.
- **Zero Raw Work Orders:** The model only knows the top 10 customers by billing. The remaining 166 work orders and their details are completely invisible.
- **Zero Chat History:** When a user replies in the chat UI, `handleSendMessage()` in `App.jsx` sends only the current text input: `askQuestion(text.trim())`. `AskRequest` schema has no `conversation_history` field. **The BI agent is 100% stateless.** Follow-up questions like *"Why did that happen?"* or *"Break that down by sector"* have zero context about previous turns.

### 6.3 Prompt Guardrails and Failure Modes
- **System Instruction Quality:**
  ```python
  "5. NEVER invent, fabricate, or extrapolate numbers not explicitly present in the metrics."
  ```
  The prompt explicitly forbids inventing figures.
- **Vulnerability to False Causality:**
  Because the context lacks deal-level notes, meeting transcripts, loss reasons, and macroeconomic variables, if a founder asks: *"Why did we lose ₹98 Crore in deals?"*, the LLM cannot establish causality from the data. Unless it explicitly declares ignorance, it will hallucinate operational causes (e.g. "pricing pressure", "competition", "delayed delivery") that do not exist in the dataset.

---

## 7. Correctness Test Matrix

| ID | Test Scenario | Expected Result | Actual Implementation Behavior | Severity | Existing Coverage | Missing Test Case Needed |
|---|---|---|---|---|---|---|
| **M-01** | Deal with `Deal Status == 'Dead'` and `Deal Stage == 'M. Projects On Hold'` (Value ₹1 Cr) | Classified as Terminal/Lost Deal; Active deals count not incremented. | Classified as **Active Deal** because status lacks literal substring `"lost"`. | **Critical** | None in `test_analytics_engine.py` | Unit test with `"Dead"`, `"Cancelled"`, and `"Dropped"` statuses. |
| **M-02** | Total Pipeline Value requested by executive | Returns active open pipeline ($₹122.52\text{ Cr}$) or explicitly labelled gross volume. | Returns **$₹230.55\text{ Cr}$**, bundling ₹98 Cr of dead/lost projects. | **Critical** | None (`test_analytics_engine.py` asserts sum without filtering) | Assertion that lost/dead deals are excluded from active pipeline KPI. |
| **M-03** | Currency value formatted as `"5 Lakh"` | Parsed to `500000.0` | Parsed to **`5.0`** ($100,000\times$ undercount). | **High** | `test_data_cleaner.py` only tests numeric commas and `$` | Test cases for `Lakh`, `Crore`, `M`, `k`, `Cr`. |
| **M-04** | Conversion Rate with 166 Won, 42 Lost, 84 Dead deals | Conversion Rate $= \frac{166}{166 + 42 + 84} = 56.85\%$ | Calculated as **$79.81\%$** ($166 / 208$), ignoring dead deals. | **Critical** | None (tests only assert formula with synthetic won/lost) | Test conversion rate denominator includes all terminal closed statuses. |
| **M-05** | Repeated Excel column header rows in dataset | Ignored or filtered during normalization. | Cleaned as row with `name='Unspecified'`, `value=0.0`. Increments `total_deals`. | **Medium** | None | Test ensuring rows where `Deal Status == 'Deal Status'` are dropped. |
| **M-06** | Multi-turn conversational question to `/ask` | Follow-up question incorporates context from previous answers. | Evaluated **statelessly**. Model has zero knowledge of prior exchanges. | **Medium** | None (`test_api.py` only sends single prompt) | Session-based integration test asserting conversation memory. |

---

## 8. Five Concrete Numerical Verifications

### Example 1: Active Deal Count & Residual Math Defect
- **Dataset Input:**
  - Total deals: $346$
  - Won deals (`str.contains("won")`): $166$
  - Lost deals (`str.contains("lost")`): $42$
- **Current Engine Calculation:**
  $$\text{active\_deals} = 346 - (166 + 42) = 138$$
- **Correct Business Math:**
  - Status `"Dead"` rows in data: $127$
  - Deals with status `"Dead"` and stage without `"lost"`: $84$
  - Truly open deals (status `"Open"`: 49, `"On Hold"`: 2, unspecified: 1): $52$
  - Falsely classified active deals: $138 - 52 = \mathbf{86\text{ deals}}$ ($165\%$ error in active deal volume).

### Example 2: Conversion Rate Calculation
- **Dataset Input:**
  - Won deals: $166$
  - Explicit `"lost"` stage deals: $42$
  - Other terminal `"Dead"` deals: $84$
- **Current Engine Calculation:**
  $$\text{conversion\_rate} = \frac{166}{166 + 42} \times 100 = \mathbf{79.81\%}$$
- **Correct Business Math:**
  $$\text{true\_closed\_deals} = 166 + 42 + 84 = 292$$
  $$\text{true\_conversion\_rate} = \frac{166}{292} \times 100 = \mathbf{56.85\%}$$
  The dashboard overstates company sales closing efficacy by $+22.96\%$.

### Example 3: Pipeline Value Contamination
- **Dataset Input Values:**
  - Deals with terminal stage `"L. Project Lost"`: $₹98,25,41,075.81$
  - Deals won: $₹9,77,30,418.98$
  - Truly active / open deals: $₹68,81,52,293.17$
  - Dead deals in non-lost stages: $₹53,70,94,252.95$
- **Current Engine Output:**
  $$\text{total\_pipeline\_value} = \mathbf{₹230,55,18,040.91}$$
- **Executive Reality:**
  - The actual active forward-looking pipeline is **₹68.82 Crore**, but the dashboard presents **₹230.55 Crore** ($335\%$ higher than actual ongoing pipeline).

### Example 4: Numeric String Parsing Loss
- **Input Data:** Deal value string `"15 Lakh"`
- **Data Cleaner Execution:**
  - `re.search(r"\d+(?:,\d+)*(?:\.\d+)?", "15 Lakh")` matches `"15"`
  - `float("15")` returns `15.0`
- **Discrepancy:**
  - Actual intended monetary value: $₹15,00,000.00$
  - Output recorded in DataFrame: $₹15.00$
  - Mathematical error factor: $\mathbf{100,000\times}$ under-reporting.

### Example 5: Work Order Unbilled Backlog Calculation
- **Input Data:**
  - `total_contract_value`: $₹21,16,49,409.21$
  - `total_billed`: $₹10,73,89,776.59$
- **Current Engine Execution:**
  $$\text{total\_unbilled} = 211649409.21 - 107389776.59 = \mathbf{₹10,42,59,632.62}$$
  $$\text{billing\_percentage} = \frac{107389776.59}{211649409.21} \times 100 = \mathbf{50.74\%}$$
- **Verification:**
  - Sum of unbilled + billed equals total contract ($₹10.74\text{ Cr} + ₹10.43\text{ Cr} = ₹21.16\text{ Cr}$).
  - Calculation is mathematically verified and robust.

---

## 9. Prioritized Remediation Plan

### Priority 1: Immediate KPI Correctness Fixes
1. **Revise Terminal Status Matching in [`analytics_engine.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/analytics_engine.py):**
   Expand `is_lost` to include `"dead"`, `"lost"`, `"cancelled"`, `"dropped"`, and `"rejected"` across both `Deal Status` and `Deal Stage`.
2. **Disaggregate Pipeline Value Metrics:**
   Split `total_pipeline_value` into two distinct metrics:
   - `active_pipeline_value`: strictly open/in-progress deals.
   - `gross_historical_pipeline`: all historic recorded opportunities.
3. **Drop Repeated Header Rows in [`data_cleaner.py`](file:///d:/Captures/Skylarp%20drones/Skylarp-drones-Software-Building-/backend/services/data_cleaner.py):**
   Add filter `clean_df = clean_df[clean_df["Deal Status"].str.lower() != "deal status"]`.

### Priority 2: Indian Financial Unit Normalization
4. **Enhance `_clean_numeric_series`:**
   Add unit detection multipliers for `"lakh"`, `"lac"`, `"cr"`, `"crore"`, `"k"`, `"m"`, and `"million"` before converting to float.

### Priority 3: BI Agent Guardrails & State Management
5. **Contextual Status Breakdown in LLM Context:**
   Clearly present active vs. lost revenue breakdown in `_build_context()` so the model does not treat historical lost deals as prospective pipeline.
6. **Multi-Turn Chat History:**
   Extend `AskRequest` schema and `routes.py` to accept and pass `conversation_history: list[dict]` to Groq API.

