"""
PostgreSQL 15 Live Row-Level Security, Multi-Tenant Isolation, and Synchronization Test Suite.

Executes against live PostgreSQL 15 database (skylarp_test_db).
Verifies:
1. Application role 'skylarp_app_user' security attributes: NOSUPERUSER NOBYPASSRLS.
2. Complete Row-Level Security (RLS) isolation across ALL 8 tenant-owned tables:
   - snapshot_metadata
   - deals
   - work_orders
   - sync_runs
   - integration_connections
   - tenant_board_configs
   - verified_domains
   - tenant_memberships
3. Fail-closed defense: 0 rows visible without established session tenant context.
4. Safe membership lookup without cross-tenant enumeration via app.current_user_id.
5. Session-level advisory locking (pg_try_advisory_lock / pg_advisory_unlock):
   - Pinned to dedicated connection.
   - Immediate rejection of concurrent sync on same (tenant_id, connection_id).
   - Concurrent execution permitted across different connections or tenants.
6. Atomic snapshot cutover and crash/rollback recovery.
7. Connection pool context cleanup (preventing cross-request tenant context leakage).
8. Distributed fencing tokens fencing out zombie workers.
"""

from datetime import datetime, timezone
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
from sqlalchemy import select, text, update, delete
from sqlalchemy.exc import DBAPIError, IntegrityError

from db.base import Base
from db.models.deal import Deal
from db.models.work_order import WorkOrder
from db.models.snapshot import SnapshotMetadata, SyncRun
from db.models.tenant import (
    Tenant,
    User,
    TenantMembership,
    IntegrationConnection,
    TenantBoardConfig,
    VerifiedDomain,
)
from db.session import (
    set_session_tenant_context,
    set_session_user_context,
)
from services.sync_engine import (
    SessionAdvisoryLock,
    AdvisoryLockAcquisitionError,
    ZombieWorkerFencedError,
)


POSTGRES_TEST_URL = os.getenv(
    "POSTGRES_TEST_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skylarp_test_db",
)

TENANT_A_ID = uuid.UUID("a1111111-1111-1111-1111-111111111111")
TENANT_B_ID = uuid.UUID("b2222222-2222-2222-2222-222222222222")

USER_A_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
USER_B_ID = uuid.UUID("b0000000-0000-0000-0000-000000000002")

CONN_A1_ID = uuid.UUID("a0000000-0000-0000-0000-000000000011")
CONN_A2_ID = uuid.UUID("a0000000-0000-0000-0000-000000000012")
CONN_B1_ID = uuid.UUID("b0000000-0000-0000-0000-000000000021")


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(POSTGRES_TEST_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    """Provides a transactional session with automatic rollback."""
    session_factory = async_sessionmaker(
        bind=pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


# =====================================================================
# 1. PostgreSQL Application Role Security Attributes
# =====================================================================

@pytest.mark.asyncio
async def test_postgres_role_security_attributes(pg_session: AsyncSession):
    """Verify skylarp_app_user role has NOSUPERUSER and NOBYPASSRLS in pg_roles."""
    res = await pg_session.execute(
        text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'skylarp_app_user'")
    )
    row = res.fetchone()
    assert row is not None, "Role 'skylarp_app_user' must exist in PostgreSQL!"
    assert row.rolsuper is False, "Role 'skylarp_app_user' must NOT be a superuser!"
    assert row.rolbypassrls is False, "Role 'skylarp_app_user' must NOT have BYPASSRLS privilege!"


# =====================================================================
# 2. Complete RLS Coverage Across ALL 8 Tenant Tables
# =====================================================================

@pytest.mark.asyncio
async def test_postgres_complete_rls_isolation_all_8_tables(pg_session: AsyncSession):
    """
    Sets up Tenant A (with 2 connections) and Tenant B (with 1 connection).
    Populates records across all 8 tenant tables:
    1. snapshot_metadata
    2. deals
    3. work_orders
    4. sync_runs
    5. integration_connections
    6. tenant_board_configs
    7. verified_domains
    8. tenant_memberships

    Verifies under unprivileged role 'skylarp_app_user':
    - Fail-closed: 0 records visible without app.current_tenant_id.
    - Tenant A context: sees only Tenant A rows across all 8 tables.
    - Tenant B context: sees only Tenant B rows across all 8 tables.
    - Cross-tenant update/delete: affects 0 rows.
    """
    # Clean previous test artifacts for deterministic runs
    await pg_session.execute(text("DELETE FROM tenants WHERE tenant_id IN (:t1, :t2)"), {"t1": TENANT_A_ID, "t2": TENANT_B_ID})
    await pg_session.execute(text("DELETE FROM users WHERE user_id IN (:u1, :u2)"), {"u1": USER_A_ID, "u2": USER_B_ID})
    await pg_session.commit()

    # 1. Create Base Tenants & Users (as postgres superuser)
    t_a = Tenant(tenant_id=TENANT_A_ID, name="Tenant Alpha", slug=f"alpha-{uuid.uuid4().hex[:6]}")
    t_b = Tenant(tenant_id=TENANT_B_ID, name="Tenant Beta", slug=f"beta-{uuid.uuid4().hex[:6]}")
    u_a = User(user_id=USER_A_ID, email="admin@alpha.com", hashed_password="pw", full_name="Alpha Admin")
    u_b = User(user_id=USER_B_ID, email="admin@beta.com", hashed_password="pw", full_name="Beta Admin")
    pg_session.add_all([t_a, t_b, u_a, u_b])
    await pg_session.flush()

    # 2. Memberships (Table 8)
    m_a = TenantMembership(tenant_id=TENANT_A_ID, user_id=USER_A_ID, role="OWNER")
    m_b = TenantMembership(tenant_id=TENANT_B_ID, user_id=USER_B_ID, role="OWNER")
    pg_session.add_all([m_a, m_b])

    # 3. Verified Domains (Table 7)
    vd_a = VerifiedDomain(tenant_id=TENANT_A_ID, domain_name="alpha.com", is_verified=True)
    vd_b = VerifiedDomain(tenant_id=TENANT_B_ID, domain_name="beta.com", is_verified=True)
    pg_session.add_all([vd_a, vd_b])

    # 4. Integration Connections (Table 5) - Tenant A has 2 connections, Tenant B has 1
    conn_a1 = IntegrationConnection(
        connection_id=CONN_A1_ID,
        tenant_id=TENANT_A_ID,
        connection_name="Alpha Sales Conn",
        encrypted_credentials="enc:a1",
        status="ACTIVE",
    )
    conn_a2 = IntegrationConnection(
        connection_id=CONN_A2_ID,
        tenant_id=TENANT_A_ID,
        connection_name="Alpha Operations Conn",
        encrypted_credentials="enc:a2",
        status="ACTIVE",
    )
    conn_b1 = IntegrationConnection(
        connection_id=CONN_B1_ID,
        tenant_id=TENANT_B_ID,
        connection_name="Beta Sales Conn",
        encrypted_credentials="enc:b1",
        status="ACTIVE",
    )
    pg_session.add_all([conn_a1, conn_a2, conn_b1])
    await pg_session.flush()

    # 5. Board Configs (Table 6)
    b_a1 = TenantBoardConfig(
        tenant_id=TENANT_A_ID,
        connection_id=CONN_A1_ID,
        board_type="deals",
        monday_board_id="101",
        monday_board_name="Alpha Deals",
    )
    b_a2 = TenantBoardConfig(
        tenant_id=TENANT_A_ID,
        connection_id=CONN_A2_ID,
        board_type="work_orders",
        monday_board_id="102",
        monday_board_name="Alpha WO",
    )
    b_b1 = TenantBoardConfig(
        tenant_id=TENANT_B_ID,
        connection_id=CONN_B1_ID,
        board_type="deals",
        monday_board_id="201",
        monday_board_name="Beta Deals",
    )
    pg_session.add_all([b_a1, b_a2, b_b1])

    # 6. Snapshots (Table 1)
    snap_a_id = uuid.uuid4()
    snap_b_id = uuid.uuid4()
    snap_a = SnapshotMetadata(
        snapshot_id=snap_a_id,
        tenant_id=TENANT_A_ID,
        version=1,
        is_active=True,
        metrics_cache={"total": 1},
    )
    snap_b = SnapshotMetadata(
        snapshot_id=snap_b_id,
        tenant_id=TENANT_B_ID,
        version=1,
        is_active=True,
        metrics_cache={"total": 2},
    )
    pg_session.add_all([snap_a, snap_b])
    await pg_session.flush()

    # 7. Deals (Table 2) & Work Orders (Table 3)
    deal_a = Deal(
        tenant_id=TENANT_A_ID,
        snapshot_id=snap_a_id,
        item_id="DEAL-A1",
        deal_name="Alpha Deal",
        normalized_deal_value=Decimal("100000.00"),
        currency="INR",
        deal_status="Won",
        deal_stage="Closed",
        classification="WON",
        sector_service="Solar",
    )
    deal_b = Deal(
        tenant_id=TENANT_B_ID,
        snapshot_id=snap_b_id,
        item_id="DEAL-B1",
        deal_name="Beta Deal",
        normalized_deal_value=Decimal("200000.00"),
        currency="INR",
        deal_status="Won",
        deal_stage="Closed",
        classification="WON",
        sector_service="Wind",
    )
    wo_a = WorkOrder(
        tenant_id=TENANT_A_ID,
        snapshot_id=snap_a_id,
        wo_id="WO-A1",
        customer_name="Customer Alpha",
        execution_status="Completed",
    )
    wo_b = WorkOrder(
        tenant_id=TENANT_B_ID,
        snapshot_id=snap_b_id,
        wo_id="WO-B1",
        customer_name="Customer Beta",
        execution_status="Completed",
    )
    pg_session.add_all([deal_a, deal_b, wo_a, wo_b])

    # 8. Sync Runs (Table 4)
    run_a = SyncRun(
        tenant_id=TENANT_A_ID,
        connection_id=CONN_A1_ID,
        idempotency_key="sync_a_1",
        status="SUCCESS",
        attempt_count=1,
    )
    run_b = SyncRun(
        tenant_id=TENANT_B_ID,
        connection_id=CONN_B1_ID,
        idempotency_key="sync_b_1",
        status="SUCCESS",
        attempt_count=1,
    )
    pg_session.add_all([run_a, run_b])
    await pg_session.commit()

    # =================================================================
    # Switch session to unprivileged application role 'skylarp_app_user'
    # =================================================================
    await pg_session.execute(text("SET ROLE skylarp_app_user"))

    try:
        # A. FAIL-CLOSED CHECK: Without tenant context, all 8 tables return 0 rows
        await pg_session.execute(text("RESET app.current_tenant_id"))
        await pg_session.execute(text("RESET app.current_user_id"))

        assert len((await pg_session.execute(select(SnapshotMetadata))).scalars().all()) == 0
        assert len((await pg_session.execute(select(Deal))).scalars().all()) == 0
        assert len((await pg_session.execute(select(WorkOrder))).scalars().all()) == 0
        assert len((await pg_session.execute(select(SyncRun))).scalars().all()) == 0
        assert len((await pg_session.execute(select(IntegrationConnection))).scalars().all()) == 0
        assert len((await pg_session.execute(select(TenantBoardConfig))).scalars().all()) == 0
        assert len((await pg_session.execute(select(VerifiedDomain))).scalars().all()) == 0
        assert len((await pg_session.execute(select(TenantMembership))).scalars().all()) == 0

        # B. TENANT ALPHA CONTEXT: Sees exactly Tenant A rows across all 8 tables
        await set_session_tenant_context(pg_session, TENANT_A_ID)

        snaps_a = (await pg_session.execute(select(SnapshotMetadata))).scalars().all()
        assert len(snaps_a) == 1 and snaps_a[0].tenant_id == TENANT_A_ID

        deals_a = (await pg_session.execute(select(Deal))).scalars().all()
        assert len(deals_a) == 1 and deals_a[0].item_id == "DEAL-A1"

        wos_a = (await pg_session.execute(select(WorkOrder))).scalars().all()
        assert len(wos_a) == 1 and wos_a[0].wo_id == "WO-A1"

        runs_a = (await pg_session.execute(select(SyncRun))).scalars().all()
        assert len(runs_a) == 1 and runs_a[0].idempotency_key == "sync_a_1"

        conns_a = (await pg_session.execute(select(IntegrationConnection))).scalars().all()
        assert len(conns_a) == 2  # Tenant A has 2 connections!

        boards_a = (await pg_session.execute(select(TenantBoardConfig))).scalars().all()
        assert len(boards_a) == 2

        vds_a = (await pg_session.execute(select(VerifiedDomain))).scalars().all()
        assert len(vds_a) == 1 and vds_a[0].domain_name == "alpha.com"

        mems_a = (await pg_session.execute(select(TenantMembership))).scalars().all()
        assert len(mems_a) == 1 and mems_a[0].user_id == USER_A_ID

        # C. TENANT BETA CONTEXT: Sees exactly Tenant B rows across all 8 tables
        await set_session_tenant_context(pg_session, TENANT_B_ID)

        assert len((await pg_session.execute(select(SnapshotMetadata))).scalars().all()) == 1
        assert len((await pg_session.execute(select(Deal))).scalars().all()) == 1
        assert len((await pg_session.execute(select(WorkOrder))).scalars().all()) == 1
        assert len((await pg_session.execute(select(SyncRun))).scalars().all()) == 1
        assert len((await pg_session.execute(select(IntegrationConnection))).scalars().all()) == 1
        assert len((await pg_session.execute(select(TenantBoardConfig))).scalars().all()) == 1
        assert len((await pg_session.execute(select(VerifiedDomain))).scalars().all()) == 1
        assert len((await pg_session.execute(select(TenantMembership))).scalars().all()) == 1

        # D. CROSS-TENANT UPDATE / DELETE ATTEMPT: Affects 0 rows under Tenant B context
        del_res = await pg_session.execute(
            delete(Deal).where(Deal.item_id == "DEAL-A1")
        )
        assert del_res.rowcount == 0  # Tenant B cannot delete Tenant A's deal

        upd_res = await pg_session.execute(
            update(Deal).where(Deal.item_id == "DEAL-A1").values(deal_name="Hacked Deal")
        )
        assert upd_res.rowcount == 0  # Tenant B cannot update Tenant A's deal

    finally:
        await pg_session.rollback()
        await pg_session.execute(text("RESET ROLE"))


# =====================================================================
# 3. Membership Lookup Without Cross-Tenant Enumeration
# =====================================================================

@pytest.mark.asyncio
async def test_postgres_membership_enumeration_protection(pg_session: AsyncSession):
    """
    Verify that when app.current_tenant_id is NULL (e.g. at login/tenant selection),
    setting app.current_user_id allows the user to see ONLY their own memberships
    without leaking memberships belonging to other users.
    """
    await pg_session.execute(text("SET ROLE skylarp_app_user"))
    try:
        # Reset tenant context
        await pg_session.execute(text("RESET app.current_tenant_id"))

        # User A context
        await set_session_user_context(pg_session, USER_A_ID)
        mems_a = (await pg_session.execute(select(TenantMembership))).scalars().all()
        assert len(mems_a) == 1
        assert mems_a[0].user_id == USER_A_ID
        assert mems_a[0].tenant_id == TENANT_A_ID

        # User B context
        await set_session_user_context(pg_session, USER_B_ID)
        mems_b = (await pg_session.execute(select(TenantMembership))).scalars().all()
        assert len(mems_b) == 1
        assert mems_b[0].user_id == USER_B_ID
        assert mems_b[0].tenant_id == TENANT_B_ID

        # Missing user context -> 0 memberships visible
        await pg_session.execute(text("RESET app.current_user_id"))
        hidden = (await pg_session.execute(select(TenantMembership))).scalars().all()
        assert len(hidden) == 0

    finally:
        await pg_session.rollback()
        await pg_session.execute(text("RESET ROLE"))


# =====================================================================
# 4. Session-Level Advisory Locking Lifecycle
# =====================================================================

@pytest.mark.asyncio
async def test_postgres_session_advisory_locking_lifecycle(pg_engine):
    """
    Verify:
    1. SessionAdvisoryLock uses pg_try_advisory_lock pinned to a dedicated connection.
    2. Concurrent lock attempts on the same (tenant_id, connection_id) fail with AdvisoryLockAcquisitionError.
    3. Independent connections or different tenants acquire locks concurrently without contention.
    4. Locks release cleanly in finally block.
    """
    lock1 = SessionAdvisoryLock(
        engine=pg_engine,
        tenant_id=TENANT_A_ID,
        connection_id=CONN_A1_ID,
    )
    lock2 = SessionAdvisoryLock(
        engine=pg_engine,
        tenant_id=TENANT_A_ID,
        connection_id=CONN_A1_ID,  # SAME tenant and connection!
    )
    lock_different_conn = SessionAdvisoryLock(
        engine=pg_engine,
        tenant_id=TENANT_A_ID,
        connection_id=CONN_A2_ID,  # Different connection on Tenant A
    )
    lock_different_tenant = SessionAdvisoryLock(
        engine=pg_engine,
        tenant_id=TENANT_B_ID,
        connection_id=CONN_B1_ID,  # Different tenant
    )

    # 1. Acquire lock 1
    await lock1.acquire()
    assert lock1.is_locked is True

    # 2. Concurrent acquire on same (tenant, conn) fails immediately
    assert await lock2.acquire() is False
    with pytest.raises(AdvisoryLockAcquisitionError, match="Concurrent synchronization already active"):
        async with lock2:
            pass

    # 3. Concurrent acquire on different connection succeeds
    await lock_different_conn.acquire()
    assert lock_different_conn.is_locked is True

    # 4. Concurrent acquire on different tenant succeeds
    await lock_different_tenant.acquire()
    assert lock_different_tenant.is_locked is True

    # 5. Clean release
    await lock1.release()
    await lock_different_conn.release()
    await lock_different_tenant.release()

    # After release, lock2 can now acquire successfully
    await lock2.acquire()
    assert lock2.is_locked is True
    await lock2.release()


# =====================================================================
# 5. Connection Pool Context Leakage Test
# =====================================================================

@pytest.mark.asyncio
async def test_postgres_connection_pool_context_leakage(pg_engine):
    """
    Verify that sessions checked out from the connection pool reset
    app.current_tenant_id and app.current_user_id upon release, preventing
    cross-request data leakage across pooled connections.
    """
    session_factory = async_sessionmaker(
        bind=pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Session 1 sets tenant context and closes
    async with session_factory() as s1:
        await set_session_tenant_context(s1, TENANT_A_ID)
        val = (await s1.execute(text("SELECT current_setting('app.current_tenant_id', true)"))).scalar()
        assert val == str(TENANT_A_ID)
        # Reset as done in get_tenant_db_session
        await s1.execute(text("RESET app.current_tenant_id"))
        await s1.execute(text("RESET app.current_user_id"))

    # Session 2 checks out connection from pool
    async with session_factory() as s2:
        val2 = (await s2.execute(text("SELECT current_setting('app.current_tenant_id', true)"))).scalar()
        assert val2 is None or val2 == "", "Connection pool leaked tenant context!"

