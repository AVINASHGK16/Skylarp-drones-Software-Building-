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

from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

# Path setup for backend
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.auth_routes import auth_router
from api.routes import router as api_router
from api.demo_routes import demo_router
from services.analytics_engine import generate_dashboard_metrics
from services.bi_agent import BIAgent
from services.data_cleaner import (
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)
from services.data_loader import load_dataset
from services.demo_data import generate_synthetic_demo_dataset
from services.monday_service import MondayClient

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def initialize_demo_data(app: FastAPI) -> None:
    """
    Initialize isolated synthetic demo dataset and metrics for portfolio mode.
    Does NOT touch Monday.com, Excel files, PostgreSQL, or production tenant caches.
    """
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env")

    groq_key = os.getenv("GROQ_API_KEY")

    logger.info("Generating synthetic demo dataset for portfolio demonstration...")
    clean_deals_df, clean_wo_df, demo_metrics, demo_quality_report = generate_synthetic_demo_dataset()

    demo_metadata = {
        "data_source": "synthetic_demo",
        "data_status": "live",
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "fallback_reason": None,
    }

    demo_bi_agent = None
    if groq_key and groq_key != "your_groq_api_key_here":
        try:
            demo_bi_agent = BIAgent(api_key=groq_key)
            logger.info("BIAgent initialized for demo mode with Groq API.")
        except Exception as e:
            logger.warning("Could not initialize Groq AI for demo mode (%s). Deterministic assistant will be used.", e)

    # Store strictly in segregated demo state attributes
    app.state.demo_mode_enabled = True
    app.state.demo_metrics = demo_metrics
    app.state.demo_dataset = (clean_deals_df, clean_wo_df, demo_quality_report)
    app.state.demo_metadata = demo_metadata
    app.state.demo_bi_agent = demo_bi_agent

    # Leave production caches unpopulated / safe
    app.state.tenant_metrics_cache = {}
    app.state.tenant_bi_agents = {}
    app.state.tenant_dfs = {}
    app.state.tenant_metadata = {}

    logger.info(
        "Demo mode initialization complete: %d synthetic deals, %d work orders ready.",
        len(clean_deals_df),
        len(clean_wo_df),
    )


def initialize_app_data(app: FastAPI) -> None:
    """
    Load data from Monday.com with reliable Excel fallback during application startup,
    clean datasets, pre-compute metrics, and cache in memory.
    """
    app.state.demo_mode_enabled = False
    app.state.demo_metrics = None
    app.state.demo_dataset = None
    app.state.demo_metadata = None
    app.state.demo_bi_agent = None

    # Load environment variables from .env in backend or root
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env")

    api_key = os.getenv("MONDAY_API_KEY")
    deals_board_id = os.getenv("DEALS_BOARD_ID")
    wo_board_id = os.getenv("WORK_ORDERS_BOARD_ID")
    groq_key = os.getenv("GROQ_API_KEY")

    # Ingest data using source selection strategy with automatic Excel fallback
    raw_deals, raw_work_orders, metadata = load_dataset(
        api_key=api_key,
        deals_board_id=deals_board_id,
        wo_board_id=wo_board_id,
        root_dir=ROOT_DIR,
    )

    # Clean datasets
    logger.info("Cleaning datasets at startup...")
    deals_df = clean_deals_data(raw_deals)
    wo_df = clean_work_orders_data(raw_work_orders)

    # Handle dataset status
    if metadata.get("data_status") == "unavailable":
        logger.error(
            "Application initialized in DEGRADED/UNAVAILABLE state: %s",
            metadata.get("fallback_reason"),
        )
        dashboard_metrics = None
        quality_report = {
            "status": "unavailable",
            "total_records": 0,
            "caveats": [
                "CRITICAL: No usable dataset is available. Monday.com API and local Excel backup sources are unavailable."
            ],
        }
    else:
        logger.info("Generating quality report & pre-computing dashboard metrics...")
        quality_report = generate_data_quality_report(deals_df, wo_df)
        if metadata.get("data_status") == "fallback":
            quality_report["caveats"].insert(
                0,
                "Data Source Note: Historical Excel backup is being used; Monday.com live data is unavailable.",
            )
        dashboard_metrics = generate_dashboard_metrics(deals_df, wo_df)

    # Initialize BI Agent singleton if Groq key present
    bi_agent = None
    if groq_key and groq_key != "your_groq_api_key_here":
        try:
            bi_agent = BIAgent(api_key=groq_key)
            logger.info("BIAgent singleton successfully initialized with Groq API.")
        except Exception as e:
            logger.error("Failed to initialize BIAgent at startup: %s", e)

    # Cache objects and metadata in application state
    app.state.deals_df = deals_df
    app.state.wo_df = wo_df
    app.state.quality_report = quality_report
    app.state.dashboard_metrics = dashboard_metrics
    app.state.bi_agent = bi_agent
    app.state.data_metadata = metadata
    app.state.data_source = metadata.get("data_source", "unavailable")
    app.state.data_status = metadata.get("data_status", "unavailable")
    app.state.loaded_at = metadata.get("loaded_at")
    app.state.source_modified_at = metadata.get("source_modified_at")
    app.state.data_as_of = metadata.get("data_as_of")
    app.state.last_updated_at = metadata.get("last_updated_at")
    app.state.fallback_reason = metadata.get("fallback_reason")

    # Multi-tenant context cache initialized with default Skylarp tenant
    import uuid
    default_tenant_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    app.state.tenant_metrics_cache = {default_tenant_id: dashboard_metrics}
    app.state.tenant_bi_agents = {default_tenant_id: bi_agent}
    app.state.tenant_dfs = {default_tenant_id: (deals_df, wo_df, quality_report)}
    app.state.tenant_metadata = {default_tenant_id: metadata}

    logger.info(
        "Application state initialization complete. Status: '%s', Source: '%s', Records: %d",
        metadata.get("data_status"),
        metadata.get("data_source"),
        len(deals_df) + len(wo_df),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    demo_mode_env = os.getenv("DEMO_MODE", "false").lower() in ("true", "1")
    if demo_mode_env:
        logger.info("Initializing Business Intelligence Agent FastAPI service in DEMO_MODE...")
        initialize_demo_data(app)
    else:
        logger.info("Initializing Business Intelligence Agent FastAPI service in PRODUCTION MODE...")
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

# Include API Routers
app.include_router(auth_router, prefix="/auth")
app.include_router(demo_router)
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
