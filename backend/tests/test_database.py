"""
Database Infrastructure, Models, and Constraints Verification Tests.

Verifies:
1. Environment-aware database configuration and credential masking.
2. Exact Decimal / NUMERIC(18, 2) financial precision.
3. Raw source vs normalized data preservation.
4. Snapshot-scoped composite primary keys (snapshot_id, item_id) and (snapshot_id, wo_id).
5. Point-in-time snapshot isolation (same item_id across multiple snapshots).
6. Foreign-key cascading deletions (ON DELETE CASCADE).
7. Partial unique index on is_active (at most one active snapshot).
8. Transactional safety and atomic snapshot switching with rollback guarantees.
9. Verification across both SQLite and PostgreSQL 15 engines.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, text

from db.base import Base
from db.models.deal import Deal
from db.models.work_order import WorkOrder
from db.models.snapshot import SnapshotMetadata, SyncRun
from db.models.tenant import Tenant
from db.session import (
    check_database_connection,
    mask_db_url,
    resolve_database_url,
)

POSTGRES_TEST_URL = os.getenv(
    "POSTGRES_TEST_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skylarp_test_db",
)
SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"

DEFAULT_TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# =====================================================================
# Fixtures for SQLite
# =====================================================================

@pytest_asyncio.fixture
async def sqlite_engine():
    engine = create_async_engine(SQLITE_TEST_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_session(sqlite_engine):
    session_factory = async_sessionmaker(
        bind=sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        t = Tenant(tenant_id=DEFAULT_TENANT_ID, name="Skylarp Drones", slug="skylarp")
        session.add(t)
        await session.commit()
        yield session


# =====================================================================
# Fixtures for PostgreSQL 15
# =====================================================================

@pytest_asyncio.fixture
async def postgres_engine():
    engine = create_async_engine(POSTGRES_TEST_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()


@pytest_asyncio.fixture
async def postgres_session(postgres_engine):
    session_factory = async_sessionmaker(
        bind=postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        t = Tenant(tenant_id=DEFAULT_TENANT_ID, name="Skylarp Drones", slug="skylarp")
        session.add(t)
        await session.commit()
        yield session


# =====================================================================
# 1. Environment-Aware Configuration & Credential Masking Tests
# =====================================================================

def test_credential_masking():
    """Verify mask_db_url sanitizes sensitive credentials for secure logging."""
    url = "postgresql+asyncpg://myuser:SuperSecretPassword123@db.internal.host:5432/prod_bi"
    masked = mask_db_url(url)
    assert "SuperSecretPassword123" not in masked
    assert "myuser:****@db.internal.host:5432/prod_bi" in masked

    empty_masked = mask_db_url("")
    assert empty_masked == ""


def test_production_fail_fast_when_url_missing(monkeypatch):
    """Verify production fails fast if DATABASE_URL is missing."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured in production"):
        resolve_database_url()


def test_production_fail_fast_when_non_postgres(monkeypatch):
    """Verify production fails fast if non-PostgreSQL URL is provided."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./production.db")
    with pytest.raises(RuntimeError, match="requires a PostgreSQL database connection string"):
        resolve_database_url()


def test_development_allows_sqlite_fallback(monkeypatch):
    """Verify development permits fallback to SQLite when DATABASE_URL is omitted."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = resolve_database_url()
    assert "sqlite" in url


def test_test_environment_allows_sqlite(monkeypatch):
    """Verify test environment permits SQLite."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = resolve_database_url()
    assert "sqlite" in url


# =====================================================================
# 2. SQLite Integration Tests
# =====================================================================

@pytest.mark.asyncio
async def test_sqlite_connection_health(sqlite_engine):
    """Verify connectivity check on SQLite."""
    health = await check_database_connection(sqlite_engine)
    assert health["connected"] is True
    assert health["dialect"] == "sqlite"


@pytest.mark.asyncio
async def test_sqlite_deal_and_work_order_composite_pk(sqlite_session: AsyncSession):
    """Verify snapshot-scoped composite primary key on SQLite."""
    snap_id = uuid.uuid4()
    snap = SnapshotMetadata(
        snapshot_id=snap_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=1,
        is_active=True,
        data_source="excel_bootstrap",
        data_status="live",
        total_deals=1,
        total_work_orders=1,
        active_pipeline_value=Decimal("500000.00"),
        gross_opportunity_value=Decimal("500000.00"),
        metrics_cache={},
    )
    sqlite_session.add(snap)
    await sqlite_session.commit()

    deal = Deal(
        tenant_id=DEFAULT_TENANT_ID,
        snapshot_id=snap_id,
        item_id="item_001",
        deal_name="Mapping Deal 1",
        raw_deal_value="₹5,00,000",
        normalized_deal_value=Decimal("500000.00"),
        value_status="VALID",
        currency="INR",
        deal_status="Won",
        deal_stage="Closed",
        classification="WON",
        sector_service="Mining",
    )
    sqlite_session.add(deal)
    await sqlite_session.commit()

    # Query back
    stmt = select(Deal).where(Deal.tenant_id == DEFAULT_TENANT_ID, Deal.snapshot_id == snap_id, Deal.item_id == "item_001")
    res = await sqlite_session.execute(stmt)
    retrieved = res.scalar_one()
    assert retrieved.normalized_deal_value == Decimal("500000.00")
    assert retrieved.currency == "INR"


# =====================================================================
# 3. PostgreSQL 15 Comprehensive Integration Tests
# =====================================================================

@pytest.mark.asyncio
async def test_postgres_connection_health(postgres_engine):
    """Verify live connectivity against PostgreSQL 15 container."""
    health = await check_database_connection(postgres_engine)
    assert health["connected"] is True
    assert health["dialect"] == "postgresql"


@pytest.mark.asyncio
async def test_postgres_numeric_precision_and_raw_preservation(postgres_session: AsyncSession):
    """
    Verify:
    1. NUMERIC(18, 2) exact decimal precision without binary floating point drift.
    2. Raw string vs normalized value preservation.
    3. Native UUID and JSONB storage.
    """
    snap_id = uuid.uuid4()
    snap = SnapshotMetadata(
        snapshot_id=snap_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=1,
        is_active=True,
        data_source="monday_api",
        data_status="live",
        total_deals=1,
        total_work_orders=1,
        active_pipeline_value=Decimal("15000000.75"),
        gross_opportunity_value=Decimal("2305518040.91"),
        metrics_cache={"active_deals": 49, "sectors": ["Powerline", "Mining"]},
        quality_report_cache={"deals_count": 346},
    )
    postgres_session.add(snap)
    await postgres_session.commit()

    deal = Deal(
        tenant_id=DEFAULT_TENANT_ID,
        snapshot_id=snap_id,
        item_id="monday_item_987",
        deal_name="Solar Farm Thermal Inspection",
        raw_deal_value="₹1.500000075 Cr",
        normalized_deal_value=Decimal("15000000.75"),
        value_status="VALID",
        currency="INR",
        raw_deal_status="Won (Contract Executed)",
        deal_status="Won",
        raw_deal_stage="Stage 6 - Final Delivery",
        deal_stage="Closed Won",
        classification="WON",
        classification_reason="Executed contract confirmed",
        sector_service="Renewables",
        close_date=date(2026, 4, 1),
    )
    postgres_session.add(deal)
    await postgres_session.commit()

    stmt = select(Deal).where(Deal.tenant_id == DEFAULT_TENANT_ID, Deal.snapshot_id == snap_id, Deal.item_id == "monday_item_987")
    res = await postgres_session.execute(stmt)
    retrieved = res.scalar_one()

    # Exact decimal precision checks
    assert retrieved.normalized_deal_value == Decimal("15000000.75")
    assert isinstance(retrieved.normalized_deal_value, Decimal)
    assert str(retrieved.normalized_deal_value) == "15000000.75"

    # Raw value preservation
    assert retrieved.raw_deal_value == "₹1.500000075 Cr"
    assert retrieved.raw_deal_status == "Won (Contract Executed)"

    # Snapshot JSONB retrieval
    snap_stmt = select(SnapshotMetadata).where(SnapshotMetadata.snapshot_id == snap_id)
    snap_res = await postgres_session.execute(snap_stmt)
    retrieved_snap = snap_res.scalar_one()
    assert retrieved_snap.metrics_cache["active_deals"] == 49
    assert "Powerline" in retrieved_snap.metrics_cache["sectors"]
    assert retrieved_snap.gross_opportunity_value == Decimal("2305518040.91")


@pytest.mark.asyncio
async def test_postgres_composite_key_uniqueness_and_isolation(postgres_session: AsyncSession):
    """
    Verify:
    1. Primary key (snapshot_id, item_id) enforces uniqueness within the same snapshot.
    2. The SAME item_id can exist across different snapshots with differing point-in-time states.
    """
    snap_1_id = uuid.uuid4()
    snap_2_id = uuid.uuid4()

    s1 = SnapshotMetadata(
        snapshot_id=snap_1_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=1,
        is_active=False,
        data_source="monday_api",
        data_status="live",
        total_deals=1,
        total_work_orders=0,
        active_pipeline_value=Decimal("1000000.00"),
        gross_opportunity_value=Decimal("1000000.00"),
        metrics_cache={},
    )
    s2 = SnapshotMetadata(
        snapshot_id=snap_2_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=2,
        is_active=True,
        data_source="monday_api",
        data_status="live",
        total_deals=1,
        total_work_orders=0,
        active_pipeline_value=Decimal("2000000.00"),
        gross_opportunity_value=Decimal("2000000.00"),
        metrics_cache={},
    )
    postgres_session.add_all([s1, s2])
    await postgres_session.commit()

    # Deal in Snapshot 1: Value is 10 Lakhs, Status is OPEN
    deal_snap1 = Deal(
        tenant_id=DEFAULT_TENANT_ID,
        snapshot_id=snap_1_id,
        item_id="DEAL-444",
        deal_name="Transmission Line Survey",
        raw_deal_value="₹10,00,000",
        normalized_deal_value=Decimal("1000000.00"),
        value_status="VALID",
        currency="INR",
        deal_status="In Progress",
        deal_stage="Proposal Sent",
        classification="OPEN",
        sector_service="Powerline",
    )
    postgres_session.add(deal_snap1)
    await postgres_session.commit()

    # Deal in Snapshot 2: Same item_id, but value revised to 20 Lakhs, Status WON
    deal_snap2 = Deal(
        tenant_id=DEFAULT_TENANT_ID,
        snapshot_id=snap_2_id,
        item_id="DEAL-444",
        deal_name="Transmission Line Survey",
        raw_deal_value="₹20,00,000",
        normalized_deal_value=Decimal("2000000.00"),
        value_status="VALID",
        currency="INR",
        deal_status="Won",
        deal_stage="Contract Signed",
        classification="WON",
        sector_service="Powerline",
    )
    postgres_session.add(deal_snap2)
    await postgres_session.commit()

    # Verify both snapshots retain their independent historical representations
    res1 = await postgres_session.execute(
        select(Deal).where(Deal.tenant_id == DEFAULT_TENANT_ID, Deal.snapshot_id == snap_1_id, Deal.item_id == "DEAL-444")
    )
    d1 = res1.scalar_one()
    assert d1.normalized_deal_value == Decimal("1000000.00")
    assert d1.classification == "OPEN"

    res2 = await postgres_session.execute(
        select(Deal).where(Deal.tenant_id == DEFAULT_TENANT_ID, Deal.snapshot_id == snap_2_id, Deal.item_id == "DEAL-444")
    )
    d2 = res2.scalar_one()
    assert d2.normalized_deal_value == Decimal("2000000.00")
    assert d2.classification == "WON"

    # Verify inserting duplicate (snapshot_1_id, 'DEAL-444') violates primary key constraint
    # Using raw SQL insertion to test the engine's PK constraint without ORM identity map conflict
    with pytest.raises(IntegrityError):
        await postgres_session.execute(
            text(
                "INSERT INTO deals (tenant_id, snapshot_id, item_id, deal_name, classification, sector_service, value_status, currency, deal_status, deal_stage, is_deleted, created_at, updated_at) "
                "VALUES (:tid, :sid, 'DEAL-444', 'Duplicate Deal', 'OPEN', 'Powerline', 'VALID', 'INR', 'Duplicate', 'Duplicate', false, NOW(), NOW())"
            ),
            {"tid": DEFAULT_TENANT_ID, "sid": snap_1_id},
        )
        await postgres_session.commit()
    await postgres_session.rollback()


@pytest.mark.asyncio
async def test_postgres_foreign_key_cascades(postgres_session: AsyncSession):
    """
    Verify deleting a SnapshotMetadata automatically cascades and purges
    all owned Deal and WorkOrder records.
    """
    snap_id = uuid.uuid4()
    snap = SnapshotMetadata(
        snapshot_id=snap_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=1,
        is_active=False,
        data_source="monday_api",
        data_status="live",
        total_deals=1,
        total_work_orders=1,
        active_pipeline_value=Decimal("100000.00"),
        gross_opportunity_value=Decimal("100000.00"),
        metrics_cache={},
    )
    deal = Deal(
        tenant_id=DEFAULT_TENANT_ID,
        snapshot_id=snap_id,
        item_id="cascade_deal_1",
        deal_name="Cascade Deal",
        raw_deal_value="₹1,00,000",
        normalized_deal_value=Decimal("100000.00"),
        value_status="VALID",
        currency="INR",
        deal_status="Won",
        deal_stage="Won",
        classification="WON",
        sector_service="Aviation",
    )
    wo = WorkOrder(
        tenant_id=DEFAULT_TENANT_ID,
        snapshot_id=snap_id,
        wo_id="cascade_wo_1",
        customer_name="Test Customer",
        total_contract_value=Decimal("100000.00"),
        billed_amount=Decimal("50000.00"),
        unbilled_amount=Decimal("50000.00"),
        value_status="VALID",
    )

    postgres_session.add(snap)
    await postgres_session.flush()
    postgres_session.add_all([deal, wo])
    await postgres_session.commit()

    # Delete snapshot
    await postgres_session.delete(snap)
    await postgres_session.commit()

    # Verify deal and work order were cascaded
    deal_check = await postgres_session.execute(
        select(Deal).where(Deal.snapshot_id == snap_id)
    )
    assert deal_check.scalars().all() == []

    wo_check = await postgres_session.execute(
        select(WorkOrder).where(WorkOrder.snapshot_id == snap_id)
    )
    assert wo_check.scalars().all() == []


@pytest.mark.asyncio
async def test_postgres_partial_unique_index_active_snapshot(postgres_session: AsyncSession):
    """
    Verify PostgreSQL enforces the partial unique index uq_active_snapshot_flag:
    At most one snapshot may have is_active = True simultaneously per tenant.
    """
    s1 = SnapshotMetadata(
        snapshot_id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        version=1,
        is_active=True,
        data_source="monday_api",
        data_status="live",
        total_deals=0,
        total_work_orders=0,
        active_pipeline_value=Decimal("0.00"),
        gross_opportunity_value=Decimal("0.00"),
        metrics_cache={},
    )
    postgres_session.add(s1)
    await postgres_session.commit()

    # Attempt to insert second snapshot with is_active = True
    s2 = SnapshotMetadata(
        snapshot_id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        version=2,
        is_active=True,
        data_source="monday_api",
        data_status="live",
        total_deals=0,
        total_work_orders=0,
        active_pipeline_value=Decimal("0.00"),
        gross_opportunity_value=Decimal("0.00"),
        metrics_cache={},
    )
    postgres_session.add(s2)
    with pytest.raises(IntegrityError):
        await postgres_session.commit()
    await postgres_session.rollback()


@pytest.mark.asyncio
async def test_postgres_atomic_snapshot_cutover_and_rollback(postgres_session: AsyncSession):
    """
    Verify transactional cutover:
    1. Atomic swap of active snapshot in a single transaction succeeds.
    2. If a transaction encounters an error and rolls back, the previous
       active snapshot remains cleanly untouched.
    """
    s1_id = uuid.uuid4()
    s2_id = uuid.uuid4()

    s1 = SnapshotMetadata(
        snapshot_id=s1_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=1,
        is_active=True,
        data_source="monday_api",
        data_status="live",
        total_deals=344,
        total_work_orders=42,
        active_pipeline_value=Decimal("688152293.17"),
        gross_opportunity_value=Decimal("2305518040.91"),
        metrics_cache={},
    )
    s2 = SnapshotMetadata(
        snapshot_id=s2_id,
        tenant_id=DEFAULT_TENANT_ID,
        version=2,
        is_active=False,
        data_source="monday_api",
        data_status="live",
        total_deals=346,
        total_work_orders=43,
        active_pipeline_value=Decimal("700000000.00"),
        gross_opportunity_value=Decimal("2320000000.00"),
        metrics_cache={},
    )
    postgres_session.add_all([s1, s2])
    await postgres_session.commit()

    # 1. Successful atomic switch
    await postgres_session.execute(
        text("UPDATE snapshot_metadata SET is_active = FALSE WHERE snapshot_id = :id"),
        {"id": s1_id},
    )
    await postgres_session.execute(
        text("UPDATE snapshot_metadata SET is_active = TRUE WHERE snapshot_id = :id"),
        {"id": s2_id},
    )
    await postgres_session.commit()

    # Verify s2 is active, s1 is inactive
    active_stmt = select(SnapshotMetadata).where(SnapshotMetadata.is_active == True)
    active_res = await postgres_session.execute(active_stmt)
    active_snap = active_res.scalar_one()
    assert active_snap.snapshot_id == s2_id

    # 2. Failed transaction with rollback: active snapshot remains s2
    try:
        await postgres_session.execute(
            text("UPDATE snapshot_metadata SET is_active = FALSE WHERE snapshot_id = :id"),
            {"id": s2_id},
        )
        # Deliberate failure: syntax error or abort
        raise ValueError("Simulated ingestion pipeline error!")
    except ValueError:
        await postgres_session.rollback()

    # Verify active snapshot is still s2 (rollback preserved state)
    active_res = await postgres_session.execute(active_stmt)
    assert active_res.scalar_one().snapshot_id == s2_id


def test_alembic_migration_roundtrip_sqlite(tmp_path):
    """Verify Alembic applies full migration sequence and downgrades cleanly on SQLite."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"
    test_db_file = tmp_path / "test_migration_sqlite.db"
    test_url = f"sqlite+aiosqlite:///{test_db_file}"

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_url)

    # Upgrade to head (revisions 418a1a68bcfb and 8185cee60cff)
    command.upgrade(alembic_cfg, "head")
    assert test_db_file.exists()

    # Downgrade to base
    command.downgrade(alembic_cfg, "base")


def test_alembic_migration_roundtrip_postgres():
    """Verify Alembic applies full migration sequence and downgrades cleanly on PostgreSQL 15."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import asyncio
    import asyncpg

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"

    # Reset public schema on PostgreSQL for a completely clean Alembic migration run
    async def reset_schema():
        conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/skylarp_test_db")
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.close()

    asyncio.run(reset_schema())

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", POSTGRES_TEST_URL)

    # 1. Upgrade from clean base to head (applies initial_schema + composite_pks)
    command.upgrade(alembic_cfg, "head")

    # 2. Downgrade from head to base (tests complete rollback)
    command.downgrade(alembic_cfg, "base")

    # 3. Re-upgrade from base to head
    command.upgrade(alembic_cfg, "head")
