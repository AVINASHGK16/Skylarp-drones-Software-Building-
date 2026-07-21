"""
Main FastAPI Application Entry Point.
Initializes configuration, pre-caches backend services during startup,
and sets up CORS middleware and APIRouter.
"""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

# Path setup for backend
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.routes import router as api_router
from services.analytics_engine import generate_dashboard_metrics
from services.bi_agent import BIAgent
from services.data_cleaner import (
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)
from services.monday_service import MondayClient

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def initialize_app_data(app: FastAPI) -> None:
    """
    Load data from Monday.com or local Excel files during application startup,
    clean datasets, pre-compute metrics, and cache in memory.
    """
    # Load environment variables from .env in backend or root
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env")

    api_key = os.getenv("MONDAY_API_KEY")
    deals_board_id = os.getenv("DEALS_BOARD_ID")
    wo_board_id = os.getenv("WORK_ORDERS_BOARD_ID")
    groq_key = os.getenv("GROQ_API_KEY")

    raw_deals: list[dict] = []
    raw_work_orders: list[dict] = []

    # Check if Monday API credentials exist
    if (
        api_key
        and deals_board_id
        and wo_board_id
        and api_key != "your_monday_api_key_here"
    ):
        logger.info("--- STARTUP MODE: LIVE MONDAY.COM API ---")
        try:
            client = MondayClient(api_key=api_key)
            logger.info("Fetching Deals board items from Monday.com...")
            raw_deals_items = client.fetch_board_items(deals_board_id)
            raw_deals = client.parse_items_to_dicts(raw_deals_items)

            logger.info("Fetching Work Orders board items from Monday.com...")
            raw_wo_items = client.fetch_board_items(wo_board_id)
            raw_work_orders = client.parse_items_to_dicts(raw_wo_items)
        except Exception as e:
            logger.error("Error fetching data from Monday.com API: %s", e)
            raw_deals = []
            raw_work_orders = []
    else:
        logger.info("--- STARTUP MODE: LOCAL EXCEL FALLBACK ---")
        deal_file = ROOT_DIR / "Deal funnel Data.xlsx"
        wo_file = ROOT_DIR / "Work_Order_Tracker Data.xlsx"

        if deal_file.exists() and wo_file.exists():
            logger.info("Loading local Excel file: %s", deal_file)
            raw_deals = pd.read_excel(deal_file).to_dict(orient="records")

            logger.info("Loading local Excel file: %s", wo_file)
            raw_work_orders = pd.read_excel(wo_file, header=1).to_dict(
                orient="records"
            )
        else:
            logger.warning(
                "Neither API keys nor local Excel files were found at startup."
            )

    # Clean datasets
    logger.info("Cleaning datasets at startup...")
    deals_df = clean_deals_data(raw_deals)
    wo_df = clean_work_orders_data(raw_work_orders)

    # Generate quality report & dashboard metrics
    logger.info("Generating quality report & pre-computing dashboard metrics...")
    quality_report = generate_data_quality_report(deals_df, wo_df)
    dashboard_metrics = generate_dashboard_metrics(deals_df, wo_df)

    # Initialize BI Agent singleton if Groq key present
    bi_agent = None
    if groq_key and groq_key != "your_groq_api_key_here":
        try:
            bi_agent = BIAgent(api_key=groq_key)
            logger.info("BIAgent singleton successfully initialized with Groq API.")
        except Exception as e:
            logger.error("Failed to initialize BIAgent at startup: %s", e)

    # Cache objects in application state
    app.state.deals_df = deals_df
    app.state.wo_df = wo_df
    app.state.quality_report = quality_report
    app.state.dashboard_metrics = dashboard_metrics
    app.state.bi_agent = bi_agent
    logger.info(
        "Application state initialization complete. Processed %d total records.",
        len(deals_df) + len(wo_df),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    logger.info("Initializing Business Intelligence Agent FastAPI service...")
    initialize_app_data(app)
    yield
    logger.info("Shutting down Business Intelligence Agent API service.")


app = FastAPI(
    title="Business Intelligence Agent API",
    description="REST API service exposing business analytics, quality reports, and AI Agent insights.",
    version="1.0.0",
    lifespan=lifespan,
)

# Production CORS Origin Resolution
default_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

env_origins = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL")
if env_origins:
    custom_origins = [
        o.strip() for o in env_origins.split(",") if o.strip()
    ]
    allowed_origins = list(set(default_origins + custom_origins))
else:
    allowed_origins = ["*"]  # Fallback to wildcard if not configured

# Enable CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
