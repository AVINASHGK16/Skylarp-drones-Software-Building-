"""
Synthetic Demo Data Generator and Deterministic BI Assistant for Portfolio Mode.

Generates realistic, completely fictional data for Skylarp Drones portfolio demonstrations.
All names, figures, work orders, and deals are fictional and deterministically generated.
No actual customer or company records are used.
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Tuple

import numpy as np
import pandas as pd

from services.analytics_engine import generate_dashboard_metrics
from services.data_cleaner import (
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)

logger = logging.getLogger(__name__)

# Fictional companies strictly for public demonstration
DEMO_COMPANIES = [
    ("Apex Renewable Solar Ltd", "Solar Inspection"),
    ("Verdant Plains Agro Corp", "Agriculture"),
    ("TerraScan Civil Infrastructure", "Infrastructure"),
    ("AeroMining Geosurvey LLC", "Mining & Surveying"),
    ("Skyline Highrise Inspections", "Infrastructure"),
    ("GreenField Precision Farming", "Agriculture"),
    ("Helios Photovoltaic Farms", "Solar Inspection"),
    ("Summit Quarry Systems", "Mining & Surveying"),
]

DEMO_STAGES = ["Won", "Proposal", "Qualified", "Lost"]
STAGE_PROBABILITIES = [0.45, 0.25, 0.20, 0.10]


def generate_synthetic_demo_dataset() -> Tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    """
    Deterministically generate synthetic Deals and Work Orders DataFrames,
    clean them, and calculate dashboard metrics and quality report.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
            (clean_deals_df, clean_wo_df, dashboard_metrics, quality_report)
    """
    rng = np.random.default_rng(seed=42)  # Deterministic seed for reproducible metrics
    base_date = datetime(2026, 1, 15, tzinfo=timezone.utc)

    deals_rows = []
    wo_rows = []

    deal_id_counter = 1001
    wo_id_counter = 5001

    for company_name, sector in DEMO_COMPANIES:
        # Generate 4-7 deals per company
        num_deals = rng.integers(4, 8)
        for i in range(num_deals):
            deal_id = f"DEMO-D{deal_id_counter}"
            deal_id_counter += 1

            deal_name = f"{company_name.split()[0]} - {sector} Survey Flight #{i+1}"
            deal_val = float(rng.integers(15000, 185000))
            stage = rng.choice(DEMO_STAGES, p=STAGE_PROBABILITIES)
            prob = 100 if stage == "Won" else (0 if stage == "Lost" else int(rng.choice([30, 50, 70])))
            close_delta = int(rng.integers(10, 180))
            close_date = (base_date + timedelta(days=close_delta)).strftime("%Y-%m-%d")

            status = "Won" if stage == "Won" else ("Dead" if stage == "Lost" else "Open")

            deals_rows.append({
                "id": deal_id,
                "name": deal_name,
                "Customer Name Code": company_name,
                "Masked Deal value": str(deal_val),
                "Deal Status": status,
                "Deal Stage": stage,
                "Sector/service": sector,
                "Close Date (A)": close_date,
                "Closure Probability": str(prob),
                "Lead Source": "Portfolio Demo Ingestion",
            })

            # For Won deals, generate 1-3 correlated work orders
            if stage == "Won":
                num_wos = rng.integers(1, 4)
                split_val = deal_val / num_wos
                for j in range(num_wos):
                    wo_id = f"DEMO-WO{wo_id_counter}"
                    wo_id_counter += 1

                    wo_name = f"{deal_name} - Sortie {j+1}"
                    wo_status = rng.choice(["Completed", "In Progress", "Scheduled"], p=[0.6, 0.25, 0.15])
                    deliv_delta = close_delta + int(rng.integers(5, 45))
                    deliv_date = (base_date + timedelta(days=deliv_delta)).strftime("%Y-%m-%d")
                    
                    if wo_status == "Completed":
                        invoiced = split_val
                        pay_status = rng.choice(["Paid", "Partially Paid", "Pending"], p=[0.7, 0.2, 0.1])
                    elif wo_status == "In Progress":
                        invoiced = split_val * 0.5
                        pay_status = "Partially Paid"
                    else:
                        invoiced = 0.0
                        pay_status = "Pending"

                    wo_rows.append({
                        "id": wo_id,
                        "name": wo_name,
                        "Deal name masked": deal_name,
                        "Customer Name Code": company_name,
                        "Execution Status": wo_status,
                        "Probable Start Date": (base_date + timedelta(days=close_delta)).strftime("%Y-%m-%d"),
                        "Probable End Date": deliv_date,
                        "Data Delivery Date": deliv_date if wo_status == "Completed" else None,
                        "Amount in Rupees (Excl of GST) (Masked)": str(split_val),
                        "Billed Value in Rupees (Excl of GST.) (Masked)": str(invoiced),
                        "Sector": sector,
                    })

    raw_deals_list = deals_rows
    raw_wo_list = wo_rows

    clean_deals_df = clean_deals_data(raw_deals_list)
    clean_wo_df = clean_work_orders_data(raw_wo_list)

    dashboard_metrics = generate_dashboard_metrics(clean_deals_df, clean_wo_df)
    quality_report = generate_data_quality_report(clean_deals_df, clean_wo_df)

    quality_report["caveats"].insert(
        0,
        "PORTFOLIO DEMO: Displaying synthetic demonstration data. Proprietary Skylarp Drones tenant data is protected."
    )

    logger.info(
        "Generated synthetic demo dataset: %d deals, %d work orders.",
        len(clean_deals_df),
        len(clean_wo_df),
    )

    return clean_deals_df, clean_wo_df, dashboard_metrics, quality_report


def generate_deterministic_demo_answer(question: str, demo_metrics: dict[str, Any]) -> str:
    """
    Produce a deterministic, factually grounded response strictly using the
    pre-computed demo metrics when the Groq AI service is unavailable or unconfigured.

    Never invents numbers or extrapolates beyond the demo metrics.
    """
    pipeline = demo_metrics.get("pipeline_summary", {})
    revenue_stage = demo_metrics.get("revenue_by_stage", {})
    revenue_sector = demo_metrics.get("revenue_by_sector", {})
    billing = demo_metrics.get("billing_summary", {})
    wo_summary = demo_metrics.get("work_order_summary", {})
    top_cust = demo_metrics.get("top_customers", [])

    q_lower = question.lower().strip()

    # Total Pipeline / Pipeline summary query
    if any(k in q_lower for k in ["pipeline", "deal", "total value", "how much"]):
        total_val = pipeline.get("total_pipeline_value", 0.0)
        active_val = pipeline.get("active_pipeline_value", 0.0)
        deal_count = pipeline.get("total_deals", 0)
        won_deals = pipeline.get("won_deal_count", 0)
        won_rev = revenue_stage.get("Won", 0.0) if isinstance(revenue_stage, dict) else 0.0
        return (
            f"Based on the synthetic portfolio demonstration dataset:\n\n"
            f"- **Total Pipeline Value**: INR {total_val:,.2f} across {deal_count} total deals.\n"
            f"- **Active Pipeline Value**: INR {active_val:,.2f}.\n"
            f"- **Closed Won Revenue**: INR {won_rev:,.2f} ({won_deals} closed deals).\n\n"
            f"The sales pipeline demonstrates healthy stage progression across commercial drone inspection opportunities."
        )

    # Sector query
    if any(k in q_lower for k in ["sector", "industry", "agriculture", "solar", "infrastructure"]):
        sectors_str = "\n".join(
            f"- **{sec}**: INR {rev:,.2f}"
            for sec, rev in revenue_sector.items()
        )
        return (
            f"Here is the revenue breakdown by sector from the demonstration data:\n\n"
            f"{sectors_str}\n\n"
            f"Commercial drone operations in Solar Inspection and Agriculture form the largest share of deal activity."
        )

    # Billing / Invoiced / Collection query
    if any(k in q_lower for k in ["billing", "invoice", "payment", "collected", "revenue"]):
        total_contract = billing.get("total_contract_value", 0.0)
        total_billed = billing.get("total_billed", 0.0)
        unbilled = billing.get("total_unbilled", 0.0)
        billing_pct = billing.get("billing_percentage", 0.0)
        return (
            f"The billing and collections summary indicates:\n\n"
            f"- **Total Contract Value**: INR {total_contract:,.2f}\n"
            f"- **Total Billed**: INR {total_billed:,.2f}\n"
            f"- **Unbilled Backlog**: INR {unbilled:,.2f}\n"
            f"- **Billed Percentage**: {billing_pct:.1f}%\n\n"
            f"Operational cash flows remain strong with active work orders converting efficiently into billings."
        )

    # Work Order / Execution query
    if any(k in q_lower for k in ["work order", "execution", "operational", "completion", "deliver"]):
        total_wos = wo_summary.get("total_work_orders", 0)
        completed = wo_summary.get("completed_work_orders", 0)
        ongoing = wo_summary.get("ongoing_work_orders", 0)
        pending = wo_summary.get("pending_work_orders", 0)
        rate = wo_summary.get("completion_rate", 0.0)
        return (
            f"Work order operational performance overview:\n\n"
            f"- **Total Work Orders**: {total_wos}\n"
            f"- **Completed Sorties**: {completed}\n"
            f"- **Ongoing**: {ongoing}\n"
            f"- **Pending**: {pending}\n"
            f"- **Completion Rate**: {rate:.1f}%\n\n"
            f"Flight and inspection missions are being dispatched on schedule across active customer sites."
        )

    # Top Customer query
    if any(k in q_lower for k in ["customer", "client", "top", "account"]):
        cust_lines = "\n".join(
            f"- **{c.get('customer')}**: INR {c.get('revenue', 0.0):,.2f}"
            for c in top_cust[:5]
        )
        return (
            f"Top customers ranked by synthetic billed revenue:\n\n"
            f"{cust_lines}\n\n"
            f"Account concentration is well-diversified among utility-scale solar operators and civil surveying partners."
        )

    # General overview default
    total_val = pipeline.get("total_pipeline_value", 0.0)
    won_rev = revenue_stage.get("Won", 0.0) if isinstance(revenue_stage, dict) else 0.0
    return (
        f"**Executive Portfolio Overview**:\n\n"
        f"- Total pipeline stands at **INR {total_val:,.2f}**, with **INR {won_rev:,.2f}** in closed-won revenue.\n"
        f"- Operational execution reports **{wo_summary.get('completed_work_orders', 0)}** completed sorties and **{billing.get('billing_percentage', 0.0):.1f}%** billing progress.\n\n"
        f"You can ask specific questions regarding sector breakdown, sales pipeline, billing, or operational work orders."
    )
