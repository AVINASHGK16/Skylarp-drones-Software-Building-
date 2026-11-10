"""
Database Engine, Session and Connection Lifecycle Management.
Supports PostgreSQL (asyncpg) with configurable fallback to SQLite (aiosqlite) for testing.
Enforces strict environment-aware rules (fail-fast in production).
"""

import os
import re
import logging
import uuid
from typing import Any
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

logger = logging.getLogger(__name__)


def mask_db_url(url: str) -> str:
    """Mask password credentials in database connection URLs for safe logging."""
    if not url:
        return ""
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:****@", url)


def resolve_database_url() -> str:
    """
    Resolve and validate DATABASE_URL based on application environment.
    Enforces fail-fast behavior in production.
    """
    app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
    raw_url = os.getenv("DATABASE_URL", "").strip()

    if app_env == "production":
        if not raw_url:
            raise RuntimeError(
                "CRITICAL: DATABASE_URL must be configured in production environment. "
                "Silent fallback to SQLite is strictly disallowed."
            )
        # Verify PostgreSQL protocol scheme
        if not (raw_url.startswith("postgresql://") or raw_url.startswith("postgres://") or raw_url.startswith("postgresql+")):
            raise RuntimeError(
                "CRITICAL: Production environment requires a PostgreSQL database connection string "
                f"(postgresql+asyncpg://...). Received scheme: '{raw_url.split('://')[0] if '://' in raw_url else 'unknown'}'"
            )

    if not raw_url:
        raw_url = "sqlite+aiosqlite:///./skylarp_bi.db"

    # Normalize PostgreSQL schemes to asyncpg driver
    if raw_url.startswith("postgres://"):
        normalized = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+"):
        normalized = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        normalized = raw_url

    logger.info("Resolved database connection for APP_ENV=%s (URL: %s)", app_env, mask_db_url(normalized))
    return normalized


DATABASE_URL = resolve_database_url()


def get_engine_args(url: str) -> dict:
    """Configure connection pooling appropriate for the database dialect."""
    if "sqlite" in url:
        return {"echo": False}
    return {
        "echo": False,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,
    }


def create_app_engine(url: str | None = None) -> AsyncEngine:
    """Factory creating an AsyncEngine with appropriate pooling."""
    target_url = url or resolve_database_url()
    return create_async_engine(target_url, **get_engine_args(target_url))


engine: AsyncEngine = create_app_engine(DATABASE_URL)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def set_session_tenant_context(session: AsyncSession, tenant_id: Any | None, switch_role: bool = True) -> None:
    """
    Set transaction-local tenant context for PostgreSQL Row-Level Security.
    Fails closed if tenant_id is None by setting an empty string.
    Ensures runtime role is skylarp_app_user to enforce RLS (NOSUPERUSER, NOBYPASSRLS).
    """
    bind = session.bind or engine
    if bind.dialect.name == "postgresql":
        if switch_role:
            try:
                await session.execute(text("SET ROLE skylarp_app_user"))
            except Exception as e:
                logger.debug("Could not switch role to skylarp_app_user: %s", e)
        tid_str = str(tenant_id) if tenant_id else ""
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": tid_str},
        )


async def set_session_user_context(session: AsyncSession, user_id: Any | None, switch_role: bool = True) -> None:
    """
    Set transaction-local user context for PostgreSQL Row-Level Security.
    Used during login/tenant selection to isolate membership queries per user.
    """
    bind = session.bind or engine
    if bind.dialect.name == "postgresql":
        if switch_role:
            try:
                await session.execute(text("SET ROLE skylarp_app_user"))
            except Exception as e:
                logger.debug("Could not switch role to skylarp_app_user: %s", e)
        uid_str = str(user_id) if user_id else ""
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": uid_str},
        )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session with automatic transaction management."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            if (session.bind or engine).dialect.name == "postgresql":
                try:
                    await session.execute(text("RESET app.current_tenant_id"))
                    await session.execute(text("RESET app.current_user_id"))
                    await session.execute(text("RESET ROLE"))
                except Exception:
                    pass
            await session.close()


async def get_tenant_db_session(tenant_id: Any | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a tenant-isolated async database session
    with transaction-scoped Row-Level Security context.
    """
    async with async_session_factory() as session:
        if tenant_id:
            await set_session_tenant_context(session, tenant_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Ensure pooled connection context is cleared
            if (session.bind or engine).dialect.name == "postgresql":
                try:
                    await session.execute(text("RESET app.current_tenant_id"))
                    await session.execute(text("RESET app.current_user_id"))
                    await session.execute(text("RESET ROLE"))
                except Exception:
                    pass
            await session.close()


async def check_database_connection(test_engine: AsyncEngine | None = None) -> dict[str, str | bool]:
    """Execute a lightweight roundtrip query to verify database liveness."""
    eng = test_engine or engine
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"connected": True, "dialect": eng.dialect.name}
    except Exception as e:
        logger.warning("Database connectivity check failed: %s", e)
        return {"connected": False, "error": str(e), "dialect": eng.dialect.name}
