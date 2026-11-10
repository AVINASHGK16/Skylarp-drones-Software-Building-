"""
Business Analytics Engine for Monday.com BI Agent.
This module processes cleaned Deals and Work Orders DataFrames from data_cleaner.py
and computes key performance indicators (KPIs), metrics, and summaries.

This module is deterministic, side-effect free, and returns JSON-serializable structures.
"""

import logging
from typing import Any

import pandas as pd

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# Private Helper Functions
# ============================================================================


def _safe_get_column(
    df: pd.DataFrame, col_name: str, default_value: Any = None
) -> pd.Series:
    """
    Safely retrieve a column Series from a DataFrame without raising KeyError.

    Args:
        df: Input DataFrame.
        col_name: Name of column to retrieve.
        default_value: Value to populate if column is missing.

    Returns:
        pd.Series: Column series or default-filled series.
    """
    if df is None or df.empty:
        return pd.Series(dtype=object)
    if col_name in df.columns:
        return df[col_name]
    return pd.Series([default_value] * len(df), index=df.index)


def _safe_numeric_series(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Safely get numeric column filled with 0.0 for missing values."""
    series = _safe_get_column(df, col_name, default_value=0.0)
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


# ============================================================================
# Public Core Analytics Functions
# ============================================================================


def get_pipeline_summary(deals_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calculate high-level sales pipeline metrics from cleaned Deals data.

    Calculates:
        - gross_historical_opportunity_value: Sum of all valid opportunities (excludes header artifacts).
        - active_pipeline_value: Sum of OPEN opportunities (excludes terminal, on_hold, and inbound).
        - open_deal_count: Count of OPEN opportunities.
        - open_valued_deal_count: Count of OPEN opportunities with known valid financial values.
        - on_hold_deal_count: Count of ON_HOLD opportunities.
        - unassigned_inbound_count: Count of UNASSIGNED_INBOUND opportunities.
        - won_deal_count: Count of WON deals.
        - lost_deal_count: Count of LOST deals.
        - dead_or_abandoned_deal_count: Count of DEAD_OR_ABANDONED deals.
        - cancelled_deal_count: Count of CANCELLED deals.
        - unknown_deal_count: Count of UNKNOWN_OR_UNCLASSIFIED deals (e.g. repeated headers).
        - overall_concluded_win_rate: Won / (Won + Lost + Dead + Cancelled).
        - formal_decision_win_rate: Won / (Won + Lost).
        - value_coverage_metrics: Detailed tracking of valid, missing, and invalid deal values.

    Args:
        deals_df: Cleaned Deals DataFrame.

    Returns:
        dict: High-level pipeline metrics summary.
    """
    logger.info("Calculating pipeline summary metrics.")

    default_summary = {
        # New Explicit Operational Metrics
        "gross_historical_opportunity_value": 0.0,
        "active_pipeline_value": 0.0,
        "open_deal_count": 0,
        "open_valued_deal_count": 0,
        "on_hold_deal_count": 0,
        "unassigned_inbound_count": 0,
        "won_deal_count": 0,
        "lost_deal_count": 0,
        "dead_or_abandoned_deal_count": 0,
        "cancelled_deal_count": 0,
        "unknown_deal_count": 0,
        "overall_concluded_win_rate": None,
        "formal_decision_win_rate": None,
        "value_coverage": {
            "total_records": 0,
            "valid_numeric_count": 0,
            "missing_value_count": 0,
            "invalid_value_count": 0,
            "sum_valid_values": 0.0,
        },
        # Deprecated compatibility fields for frontend contracts
        "total_pipeline_value": 0.0,
        "average_deal_value": 0.0,
        "active_deals": 0,
        "total_deals": 0,
        "deals_won": 0,
        "deals_lost": 0,
        "pipeline_conversion_rate": 0.0,
    }

    if deals_df is None or deals_df.empty:
        logger.warning("Empty deals_df provided to get_pipeline_summary.")
        return default_summary

    df = deals_df.copy()
    total_records = len(df)

    # 1. Classification series
    if "Classification" in df.columns:
        cat_series = df["Classification"].astype(str)
    else:
        # Fallback to classify_deal if column not yet added
        from services.data_cleaner import classify_deal
        cat_series = pd.Series(
            [classify_deal(r.get("Deal Status"), r.get("Deal Stage"))[0] for _, r in df.iterrows()],
            index=df.index,
        )

    # Exclude repeated table header artifacts from valid business opportunity volume
    is_header_artifact = cat_series == "UNKNOWN_OR_UNCLASSIFIED"
    valid_deals_df = df[~is_header_artifact]

    # Numeric series and explicit value status tracking
    if "Masked Deal value_status" in df.columns:
        status_series = df["Masked Deal value_status"].astype(str)
        numeric_vals = pd.to_numeric(df["Masked Deal value"], errors="coerce")
    else:
        from services.data_cleaner import parse_numeric_value
        raw_col = _safe_get_column(df, "Masked Deal value")
        parsed_results = [parse_numeric_value(raw_col.iloc[i]) for i in range(len(df))]
        status_series = pd.Series([p.status for p in parsed_results], index=df.index)
        numeric_vals = pd.Series([p.value for p in parsed_results], index=df.index, dtype=float)

    # 2. Category masks
    is_open = cat_series == "OPEN"
    is_on_hold = cat_series == "ON_HOLD"
    is_inbound = cat_series == "UNASSIGNED_INBOUND"
    is_won = cat_series == "WON"
    is_lost = cat_series == "LOST"
    is_dead = cat_series == "DEAD_OR_ABANDONED"
    is_cancelled = cat_series == "CANCELLED"
    is_unknown = cat_series == "UNKNOWN_OR_UNCLASSIFIED"

    # Category Counts
    open_count = int(is_open.sum())
    on_hold_count = int(is_on_hold.sum())
    inbound_count = int(is_inbound.sum())
    won_count = int(is_won.sum())
    lost_count = int(is_lost.sum())
    dead_count = int(is_dead.sum())
    cancelled_count = int(is_cancelled.sum())
    unknown_count = int(is_unknown.sum())

    # 3. Value Coverage Metrics Tracking
    # Tracks VALID, MISSING, and INVALID (including UNSUPPORTED_CURRENCY)
    is_valid_value = (status_series == "VALID") & (~is_header_artifact)
    is_missing_value = (status_series == "MISSING") & (~is_header_artifact)
    is_invalid_value = status_series.isin(["INVALID", "UNSUPPORTED_CURRENCY"]) & (~is_header_artifact)

    valid_numeric_count = int(is_valid_value.sum())
    missing_value_count = int(is_missing_value.sum())
    invalid_value_count = int(is_invalid_value.sum())
    total_valid_deals = int(len(valid_deals_df))

    # Required Invariant: valid_numeric_count + missing_value_count + invalid_value_count == total_records
    assert valid_numeric_count + missing_value_count + invalid_value_count == total_valid_deals, (
        f"Coverage invariant violated: {valid_numeric_count} + {missing_value_count} + "
        f"{invalid_value_count} != {total_valid_deals}"
    )

    # Operational Pipeline Values: Only VALID numeric values contribute to sums
    gross_opportunity_val = float(numeric_vals[is_valid_value].sum())
    active_pipeline_val = float(numeric_vals[is_open & is_valid_value].sum())

    value_coverage = {
        "total_records": total_valid_deals,
        "valid_numeric_count": valid_numeric_count,
        "missing_value_count": missing_value_count,
        "invalid_value_count": invalid_value_count,
        "sum_valid_values": round(gross_opportunity_val, 2),
    }

    # 4. Win-Rate Metrics
    concluded_deals = won_count + lost_count + dead_count + cancelled_count
    overall_concluded_win_rate = (
        round((won_count / concluded_deals) * 100, 2)
        if concluded_deals > 0
        else None
    )

    formal_decision_deals = won_count + lost_count
    formal_decision_win_rate = (
        round((won_count / formal_decision_deals) * 100, 2)
        if formal_decision_deals > 0
        else None
    )

    # 5. Average Deal Value: Computed across OPEN opportunities with known VALID numeric values
    # Excludes missing and invalid values from the denominator.
    # Legitimate 0.0 values remain in the denominator.
    open_valid_vals = numeric_vals[is_open & is_valid_value]
    average_deal_value = float(open_valid_vals.mean()) if len(open_valid_vals) > 0 else 0.0

    # pipeline_conversion_rate: points to formal_decision_win_rate or overall_concluded_win_rate
    compat_conversion_rate = formal_decision_win_rate if formal_decision_win_rate is not None else 0.0

    result = {
        # Explicit Operational Metrics
        "gross_historical_opportunity_value": round(gross_opportunity_val, 2),
        "active_pipeline_value": round(active_pipeline_val, 2),
        "open_deal_count": open_count,
        "open_valued_deal_count": int(len(open_valid_vals)),
        "on_hold_deal_count": on_hold_count,
        "unassigned_inbound_count": inbound_count,
        "won_deal_count": won_count,
        "lost_deal_count": lost_count,
        "dead_or_abandoned_deal_count": dead_count,
        "cancelled_deal_count": cancelled_count,
        "unknown_deal_count": unknown_count,
        "overall_concluded_win_rate": overall_concluded_win_rate,
        "formal_decision_win_rate": formal_decision_win_rate,
        "value_coverage": value_coverage,
        # Deprecated compatibility fields maintained for frontend contracts
        "total_pipeline_value": round(gross_opportunity_val, 2),
        "average_deal_value": round(average_deal_value, 2),
        "active_deals": open_count,
        "total_deals": total_valid_deals,
        "deals_won": won_count,
        "deals_lost": lost_count,
        "pipeline_conversion_rate": compat_conversion_rate,
    }

    logger.info(
        "Pipeline summary calculated: %d total valid deals, INR %.2f gross opportunity, INR %.2f active pipeline.",
        len(valid_deals_df),
        gross_opportunity_val,
        active_pipeline_val,
    )
    return result


def get_revenue_by_sector(deals_df: pd.DataFrame) -> dict[str, float]:
    """
    Aggregate pipeline deal value grouped by Sector/Service.

    Args:
        deals_df: Cleaned Deals DataFrame.

    Returns:
        dict[str, float]: Sector titles mapped to total values, sorted descending.
    """
    logger.info("Calculating revenue breakdown by sector.")

    if deals_df is None or deals_df.empty:
        return {}

    df = deals_df.copy()
    if "Classification" in df.columns:
        df = df[df["Classification"] != "UNKNOWN_OR_UNCLASSIFIED"]

    if "Masked Deal value_status" in df.columns:
        valid_mask = df["Masked Deal value_status"] == "VALID"
        df["_val"] = df["Masked Deal value"].where(valid_mask, 0.0).fillna(0.0)
    else:
        df["_val"] = _safe_numeric_series(df, "Masked Deal value")

    df["_sector"] = _safe_get_column(df, "Sector/service", default_value="Unspecified").astype(str)

    grouped = (
        df.groupby("_sector")["_val"]
        .sum()
        .sort_values(ascending=False)
    )

    result = {str(k): round(float(v), 2) for k, v in grouped.items()}
    logger.info("Revenue by sector calculated for %d sectors.", len(result))
    return result


def get_revenue_by_stage(deals_df: pd.DataFrame) -> dict[str, float]:
    """
    Aggregate pipeline deal value grouped by Deal Stage.

    Args:
        deals_df: Cleaned Deals DataFrame.

    Returns:
        dict[str, float]: Deal stages mapped to total values, sorted descending.
    """
    logger.info("Calculating revenue breakdown by deal stage.")

    if deals_df is None or deals_df.empty:
        return {}

    df = deals_df.copy()
    if "Classification" in df.columns:
        df = df[df["Classification"] != "UNKNOWN_OR_UNCLASSIFIED"]

    if "Masked Deal value_status" in df.columns:
        valid_mask = df["Masked Deal value_status"] == "VALID"
        df["_val"] = df["Masked Deal value"].where(valid_mask, 0.0).fillna(0.0)
    else:
        df["_val"] = _safe_numeric_series(df, "Masked Deal value")

    df["_stage"] = _safe_get_column(df, "Deal Stage", default_value="Unspecified").astype(str)

    grouped = (
        df.groupby("_stage")["_val"]
        .sum()
        .sort_values(ascending=False)
    )

    result = {str(k): round(float(v), 2) for k, v in grouped.items()}
    logger.info("Revenue by stage calculated for %d stages.", len(result))
    return result


def get_monthly_pipeline(deals_df: pd.DataFrame) -> dict[str, float]:
    """
    Aggregate pipeline deal value by Close Date month (YYYY-MM).

    Args:
        deals_df: Cleaned Deals DataFrame.

    Returns:
        dict[str, float]: Month strings (YYYY-MM) mapped to values in chronological order.
    """
    logger.info("Calculating monthly pipeline breakdown.")

    if deals_df is None or deals_df.empty:
        return {}

    df = deals_df.copy()
    if "Classification" in df.columns:
        df = df[df["Classification"] != "UNKNOWN_OR_UNCLASSIFIED"]

    if "Masked Deal value_status" in df.columns:
        valid_mask = df["Masked Deal value_status"] == "VALID"
        df["_val"] = df["Masked Deal value"].where(valid_mask, 0.0).fillna(0.0)
    else:
        df["_val"] = _safe_numeric_series(df, "Masked Deal value")

    # Use Close Date (A) or fallback to Tentative Close Date or Created Date
    close_dates = _safe_get_column(df, "Close Date (A)")
    tentative_dates = _safe_get_column(df, "Tentative Close Date")
    created_dates = _safe_get_column(df, "Created Date")

    effective_dates = close_dates.fillna(tentative_dates).fillna(created_dates)

    parsed_dates = pd.to_datetime(effective_dates, errors="coerce")
    df["_month"] = parsed_dates.dt.strftime("%Y-%m")

    # Filter out missing/invalid month values
    valid_df = df.dropna(subset=["_month"])

    if valid_df.empty:
        return {}

    grouped = (
        valid_df.groupby("_month")["_val"]
        .sum()
        .sort_index(ascending=True)
    )

    result = {str(k): round(float(v), 2) for k, v in grouped.items()}
    logger.info("Monthly pipeline calculated across %d months.", len(result))
    return result


def get_work_order_summary(wo_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calculate operational status and completion metrics from Work Orders data.

    Args:
        wo_df: Cleaned Work Orders DataFrame.

    Returns:
        dict: Work order summary metrics.
    """
    logger.info("Calculating work order summary metrics.")

    default_summary = {
        "total_work_orders": 0,
        "work_orders_by_status": {},
        "completed_work_orders": 0,
        "ongoing_work_orders": 0,
        "pending_work_orders": 0,
        "completion_rate": 0.0,
    }

    if wo_df is None or wo_df.empty:
        return default_summary

    df = wo_df.copy()
    total_wo = len(df)

    status_series = _safe_get_column(df, "Execution Status", default_value="Unknown").astype(str)

    # Status distribution dictionary
    status_counts = status_series.value_counts().to_dict()
    status_distribution = {str(k): int(v) for k, v in status_counts.items()}

    # Categorize completed / ongoing / pending
    s_lower = status_series.str.lower()
    is_completed = s_lower.str.contains("completed|done|delivered|closed|finished", regex=True, na=False)
    is_ongoing = s_lower.str.contains("progress|ongoing|active|executing|wip|in-progress", regex=True, na=False)
    is_pending = s_lower.str.contains("pending|upcoming|not started|hold|draft", regex=True, na=False)

    completed_count = int(is_completed.sum())
    ongoing_count = int(is_ongoing.sum())

    # Remaining status count treated as pending/other if not explicitly matched
    matched_explicit = completed_count + ongoing_count
    pending_count = int(is_pending.sum()) if is_pending.sum() > 0 else max(0, total_wo - matched_explicit)

    completion_rate = (
        round((completed_count / total_wo) * 100, 2)
        if total_wo > 0
        else 0.0
    )

    result = {
        "total_work_orders": total_wo,
        "work_orders_by_status": status_distribution,
        "completed_work_orders": completed_count,
        "ongoing_work_orders": ongoing_count,
        "pending_work_orders": pending_count,
        "completion_rate": completion_rate,
    }

    logger.info("Work order summary calculated: %d total orders.", total_wo)
    return result


def get_billing_summary(wo_df: pd.DataFrame) -> dict[str, float]:
    """
    Calculate contract values, billed revenue, and unbilled backlog metrics.

    Args:
        wo_df: Cleaned Work Orders DataFrame.

    Returns:
        dict[str, float]: Billing metrics summary.
    """
    logger.info("Calculating billing summary metrics.")

    default_summary = {
        "total_contract_value": 0.0,
        "total_billed": 0.0,
        "total_unbilled": 0.0,
        "billing_percentage": 0.0,
    }

    if wo_df is None or wo_df.empty:
        return default_summary

    df = wo_df.copy()

    contract_vals = _safe_numeric_series(df, "Amount in Rupees (Excl of GST) (Masked)")
    billed_vals = _safe_numeric_series(df, "Billed Value in Rupees (Excl of GST.) (Masked)")

    total_contract = float(contract_vals.sum())
    total_billed = float(billed_vals.sum())
    total_unbilled = max(0.0, total_contract - total_billed)

    billing_pct = (
        round((total_billed / total_contract) * 100, 2)
        if total_contract > 0
        else 0.0
    )

    result = {
        "total_contract_value": round(total_contract, 2),
        "total_billed": round(total_billed, 2),
        "total_unbilled": round(total_unbilled, 2),
        "billing_percentage": billing_pct,
    }

    logger.info("Billing summary calculated: INR %.2f billed out of INR %.2f total contract.",
                total_billed, total_contract)
    return result


def get_top_customers(wo_df: pd.DataFrame, top_n: int = 10) -> list[dict[str, Any]]:
    """
    Rank top customers by total billed amount.

    Args:
        wo_df: Cleaned Work Orders DataFrame.
        top_n: Number of top customers to return. Defaults to 10.

    Returns:
        list[dict]: List of dictionaries containing customer name and revenue.
    """
    logger.info("Calculating top %d customers by billed revenue.", top_n)

    if wo_df is None or wo_df.empty:
        return []

    df = wo_df.copy()
    df["_billed"] = _safe_numeric_series(df, "Billed Value in Rupees (Excl of GST.) (Masked)")
    df["_cust"] = _safe_get_column(df, "Customer Name Code", default_value="Unknown").astype(str)

    grouped = (
        df.groupby("_cust")["_billed"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
    )

    result = [
        {"customer": str(cust), "revenue": round(float(rev), 2)}
        for cust, rev in grouped.items()
    ]

    logger.info("Retrieved top %d customers.", len(result))
    return result


def get_execution_metrics(wo_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calculate project execution timelines and delivery metrics.

    Args:
        wo_df: Cleaned Work Orders DataFrame.

    Returns:
        dict: Execution metrics summary.
    """
    logger.info("Calculating project execution metrics.")

    default_summary = {
        "average_project_value": 0.0,
        "projects_with_delivery_date": 0,
        "projects_missing_delivery_date": 0,
        "execution_status_distribution": {},
    }

    if wo_df is None or wo_df.empty:
        return default_summary

    df = wo_df.copy()
    total_projects = len(df)

    contract_vals = _safe_numeric_series(df, "Amount in Rupees (Excl of GST) (Masked)")
    avg_project_val = float(contract_vals.mean()) if total_projects > 0 else 0.0

    delivery_dates = _safe_get_column(df, "Data Delivery Date")
    has_delivery_date = delivery_dates.notna() & (delivery_dates.astype(str).str.strip() != "") & (delivery_dates.astype(str) != "None")

    with_delivery = int(has_delivery_date.sum())
    missing_delivery = int(total_projects - with_delivery)

    status_series = _safe_get_column(df, "Execution Status", default_value="Unknown").astype(str)
    status_dist = {str(k): int(v) for k, v in status_series.value_counts().to_dict().items()}

    result = {
        "average_project_value": round(avg_project_val, 2),
        "projects_with_delivery_date": with_delivery,
        "projects_missing_delivery_date": missing_delivery,
        "execution_status_distribution": status_dist,
    }

    logger.info("Execution metrics calculated: %d projects with delivery dates.", with_delivery)
    return result


def generate_dashboard_metrics(
    deals_df: pd.DataFrame, wo_df: pd.DataFrame
) -> dict[str, Any]:
    """
    Master function to aggregate all business analytics into a unified JSON-serializable dictionary.

    Args:
        deals_df: Cleaned Deals DataFrame.
        wo_df: Cleaned Work Orders DataFrame.

    Returns:
        dict[str, Any]: Master analytics dashboard dictionary containing all KPIs.
    """
    logger.info("Generating master business analytics dashboard metrics.")

    master_metrics = {
        "pipeline_summary": get_pipeline_summary(deals_df),
        "revenue_by_sector": get_revenue_by_sector(deals_df),
        "revenue_by_stage": get_revenue_by_stage(deals_df),
        "monthly_pipeline": get_monthly_pipeline(deals_df),
        "work_order_summary": get_work_order_summary(wo_df),
        "billing_summary": get_billing_summary(wo_df),
        "top_customers": get_top_customers(wo_df, top_n=10),
        "execution_metrics": get_execution_metrics(wo_df),
    }

    logger.info("Master business analytics dashboard metrics successfully generated.")
    return master_metrics
