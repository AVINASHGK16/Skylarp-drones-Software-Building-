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
    # MODE 1 : LIVE MONDAY API
    # -------------------------------------------------------------------------

    if api_key and deals_board_id and wo_board_id:

        logging.info("--- MODE: LIVE MONDAY.COM API ---")

        client = MondayClient(api_key=api_key)

        logging.info("Fetching Deals Board...")
        raw_deals_items = client.fetch_board_items(deals_board_id)
        raw_deals = client.parse_items_to_dicts(raw_deals_items)

        logging.info("Fetching Work Orders Board...")
        raw_wo_items = client.fetch_board_items(wo_board_id)
        raw_work_orders = client.parse_items_to_dicts(raw_wo_items)

    # -------------------------------------------------------------------------
    # MODE 2 : LOCAL EXCEL FALLBACK
    # -------------------------------------------------------------------------

    else:

        logging.info(
            "--- MODE: LOCAL EXCEL FALLBACK (No API Keys detected) ---"
        )

        deal_file = ROOT_DIR / "Deal funnel Data.xlsx"
        wo_file = ROOT_DIR / "Work_Order_Tracker Data.xlsx"

        logging.info(f"Looking for:\n{deal_file}")
        logging.info(f"Looking for:\n{wo_file}")

        if not deal_file.exists():
            logging.error(f"Deals file not found:\n{deal_file}")
            return

        if not wo_file.exists():
            logging.error(f"Work Orders file not found:\n{wo_file}")
            return

        raw_deals = pd.read_excel(deal_file).to_dict(orient="records")

        raw_work_orders = pd.read_excel(
            wo_file,
            header=1
        ).to_dict(orient="records")

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

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key != "your_gemini_api_key_here":
        print("\n")
        print("=" * 70)
        print("BI AGENT EXECUTIVE RESPONSE (LIVE GEMINI API)")
        print("=" * 70)
        from services.bi_agent import BIAgent
        agent = BIAgent(api_key=gemini_key)
        res = agent.answer_question("What are our top revenue sectors and operational risks?", deals_df, wo_df, report)
        print("\nAI Answer:\n", res.get("answer"))

    print("\n[OK] Pipeline verification completed successfully.")


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    run_verification()