import os
import sys
import logging
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Project Paths
# -----------------------------------------------------------------------------

# backend/
BACKEND_DIR = Path(__file__).resolve().parent

# Project Root/
ROOT_DIR = BACKEND_DIR.parent

# Allow imports like: from services.xxx import ...
sys.path.insert(0, str(BACKEND_DIR))

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------

load_dotenv(ROOT_DIR / ".env")

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

from services.monday_service import MondayClient
from services.data_loader import load_dataset
from services.data_cleaner import (
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)
from services.analytics_engine import generate_dashboard_metrics

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -----------------------------------------------------------------------------
# Main Verification
# -----------------------------------------------------------------------------

def run_verification():

    api_key = os.getenv("MONDAY_API_KEY")
    deals_board_id = os.getenv("DEALS_BOARD_ID")
    wo_board_id = os.getenv("WORK_ORDERS_BOARD_ID")

    logging.info(f"Project Root : {ROOT_DIR}")
    logging.info(f"Current Dir  : {Path.cwd()}")

    # -------------------------------------------------------------------------
    # MULTI-SOURCE DATA INGESTION (MONDAY API WITH EXCEL FALLBACK)
    # -------------------------------------------------------------------------

    raw_deals, raw_work_orders, metadata = load_dataset(
        api_key=api_key,
        deals_board_id=deals_board_id,
        wo_board_id=wo_board_id,
        root_dir=ROOT_DIR,
    )

    logging.info(
        f"Data Ingestion Complete: Source='{metadata['data_source']}', Status='{metadata['data_status']}'"
    )
    if metadata.get("fallback_reason"):
        logging.info(f"Fallback/Status Note: {metadata['fallback_reason']}")

    if metadata["data_status"] == "unavailable":
        logging.error("Verification halted: Both live API and Excel backup sources are unavailable.")
        return

    # -------------------------------------------------------------------------
    # DATA CLEANING
    # -------------------------------------------------------------------------

    logging.info("Cleaning Deals dataset...")
    deals_df = clean_deals_data(raw_deals)

    logging.info("Cleaning Work Orders dataset...")
    wo_df = clean_work_orders_data(raw_work_orders)

    # -------------------------------------------------------------------------
    # DISPLAY DATA
    # -------------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("DEALS DATAFRAME")
    print("=" * 70)

    print(deals_df.info())
    print("\nHead:\n")
    print(deals_df.head())

    print("\n")

    print("=" * 70)
    print("WORK ORDERS DATAFRAME")
    print("=" * 70)

    print(wo_df.info())
    print("\nHead:\n")
    print(wo_df.head())

    # -------------------------------------------------------------------------
    # QUALITY REPORT
    # -------------------------------------------------------------------------

    logging.info("Generating Data Quality Report...")

    report = generate_data_quality_report(
        deals_df,
        wo_df,
    )

    print("\n")
    print("=" * 70)
    print("DATA QUALITY REPORT")
    print("=" * 70)

    for key, value in report.items():
        if key == "caveats":
            print("\nCaveats:")
            for caveat in value:
                print(f"  - {caveat}")
        else:
            print(f"{key}: {value}")

    print("\n")
    print("=" * 70)
    print("BUSINESS ANALYTICS DASHBOARD METRICS")
    print("=" * 70)
    metrics = generate_dashboard_metrics(deals_df, wo_df)
    import json
    print(json.dumps(metrics, indent=2))

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key and groq_key != "your_groq_api_key_here":
        print("\n")
        print("=" * 70)
        print("BI AGENT EXECUTIVE RESPONSE (LIVE GROQ API)")
        print("=" * 70)
        from services.bi_agent import BIAgent
        agent = BIAgent(api_key=groq_key)
        res = agent.answer_question("What are our top revenue sectors and operational risks?", deals_df, wo_df, report)
        print("\nAI Answer:\n", res.get("answer"))

    print("\n[OK] Pipeline verification completed successfully.")


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    run_verification()
