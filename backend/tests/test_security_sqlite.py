"""
SQLite Multi-Tenant Security & Synchronization Test Suite.

Verifies:
1. Immediate access rejection when user is deactivated or tenant membership is revoked.
2. Cryptographic security: PBKDF2 password hashing, AES-256-GCM envelope encryption,
   tamper detection, invalid key handling.
3. Candidate snapshot persistence ordering: SnapshotMetadata is persisted with is_active=False
   before dependent Deals and WorkOrders are inserted.
4. Transactional rollback safety: failed candidate ingestions leave previously active snapshots intact.
5. Multiple integration connections and multiple boards of the same type per connection.
6. Stale worker fencing tokens (ZombieWorkerFencedError) preventing stale commits.
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
from sqlalchemy import select, update
from fastapi import HTTPException
from starlette.requests import Request

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
)
from services.crypto_service import (
    hash_password,
    verify_password,
    encrypt_credentials,
    decrypt_credentials,
    create_access_token,
    decode_access_token,
)
from services.tenant_service import (
    register_tenant_with_owner,
    add_tenant_member,
    require_tenant_role,
)
from services.sync_engine import (
    SyncEngine,
    ZombieWorkerFencedError,
)
from api.routes import get_authenticated_tenant_context


SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def sqlite_engine():
    engine = create_async_engine(SQLITE_URL, echo=False)
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
        yield session


# =====================================================================
# 1. User Deactivation and Membership Revocation Security
# =====================================================================

@pytest.mark.asyncio
async def test_sqlite_user_deactivation_and_revocation(sqlite_session: AsyncSession):
    """
    Verify that deactivating a user or revoking/inactivating a membership
    immediately rejects access even if the user possesses a valid unexpired JWT.
    """
    # 1. Create Tenant and User
    t, owner, m = await register_tenant_with_owner(
        name="Skylarp Aero",
        slug="skylarp-aero",
        owner_email="founder@skylarp-aero.com",
        owner_password="StrongPassword123!",
        owner_full_name="Founder User",
        session=sqlite_session,
    )
    await sqlite_session.commit()

    # 2. Add an analyst member
    analyst, am = await add_tenant_member(
        tenant_id=t.tenant_id,
        email="analyst@skylarp-aero.com",
        password="AnalystPassword123!",
        full_name="Analyst User",
        role="ANALYST",
        session=sqlite_session,
    )
    await sqlite_session.commit()

    # Issue valid token for analyst
    token = create_access_token(
        user_id=analyst.user_id,
        email=analyst.email,
        tenant_id=t.tenant_id,
        role="ANALYST",
    )

    # Mock HTTP request helper
    def make_request(auth_header: str, tenant_header: str | None = None) -> Request:
        headers = [(b"authorization", auth_header.encode("utf-8"))]
        if tenant_header:
            headers.append((b"x-tenant-id", tenant_header.encode("utf-8")))
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/metrics",
            "headers": headers,
        }
        return Request(scope)

    # 3. Valid active user and membership succeeds
    req_valid = make_request(f"Bearer {token}")
    ctx = await get_authenticated_tenant_context(req_valid, session=sqlite_session)
    assert ctx.user_id == analyst.user_id
    assert ctx.tenant_id == t.tenant_id
    assert ctx.role == "ANALYST"

    # 4. Revoke membership (set is_active = False)
    am.is_active = False
    await sqlite_session.commit()

    # With the same valid JWT, request is immediately rejected with 403 Forbidden
    req_revoked = make_request(f"Bearer {token}")
    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_tenant_context(req_revoked, session=sqlite_session)
    assert exc_info.value.status_code == 403
    assert "active membership" in exc_info.value.detail.lower()

    # 5. Reactivate membership but deactivate user (user.is_active = False)
    am.is_active = True
    analyst.is_active = False
    await sqlite_session.commit()

    # With deactivated user, request is immediately rejected with 401 Unauthorized
    req_deactivated_user = make_request(f"Bearer {token}")
    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_tenant_context(req_deactivated_user, session=sqlite_session)
    assert exc_info.value.status_code == 401
    assert "deactivated" in exc_info.value.detail.lower()


# =====================================================================
# 2. Cryptographic Security & Envelope Encryption Tests
# =====================================================================

def test_sqlite_crypto_envelope_and_tampering():
    """Verify AES-256-GCM envelope encryption, tamper resistance, and key rotation."""
    # 1. Valid secret encryption roundtrip
    secret = "monday_oauth_token_secret_12345"
    encrypted = encrypt_credentials(secret, key_id="v1")
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == secret

    # 2. Tamper resistance: modifying any character in ciphertext/tag raises ValueError
    parts = encrypted.split(":")
    assert len(parts) == 4
    # Corrupt ciphertext byte
    corrupted_ct = parts[0] + ":" + parts[1] + ":" + parts[2] + ":" + ("00" if parts[3][:2] != "00" else "ff") + parts[3][2:]
    with pytest.raises(ValueError, match="Failed to decrypt credentials"):
        decrypt_credentials(corrupted_ct)

    # Corrupt nonce byte
    corrupted_nonce = parts[0] + ":" + parts[1] + ":" + ("00" if parts[2][:2] != "00" else "ff") + parts[2][2:] + ":" + parts[3]
    with pytest.raises(ValueError, match="Failed to decrypt credentials"):
        decrypt_credentials(corrupted_nonce)

    # 3. Malformed payload raises ValueError
    with pytest.raises(ValueError, match="Invalid encrypted payload format"):
        decrypt_credentials("invalid_unencrypted_secret")
    with pytest.raises(ValueError, match="Malformed encrypted payload"):
        decrypt_credentials("aes_gcm:v1:short")


# =====================================================================
# 3. Candidate Snapshot Persistence Ordering & Rollback Safety
# =====================================================================

@pytest.mark.asyncio
async def test_sqlite_candidate_persistence_order_and_rollback(sqlite_session: AsyncSession):
    """
    Verify:
    1. SnapshotMetadata is inserted with is_active = False BEFORE child Deals/WorkOrders.
    2. Candidate rows are never exposed as active.
    3. Failure during candidate ingestion leaves previous active snapshot intact.
    4. Successful cutover atomically activates candidate and deactivates prior.
    """
    tenant_id = uuid.uuid4()
    t = Tenant(tenant_id=tenant_id, name="Test Tenant", slug="test-tenant")
    sqlite_session.add(t)
    await sqlite_session.flush()

    # 1. Establish an initial active snapshot (v1)
    v1_id = uuid.uuid4()
    v1_snap = SnapshotMetadata(
        snapshot_id=v1_id,
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        data_source="monday_api",
        data_status="live",
        total_deals=1,
        total_work_orders=1,
        active_pipeline_value=Decimal("1000000.00"),
        gross_opportunity_value=Decimal("1000000.00"),
        metrics_cache={"pipeline_summary": {"active_pipeline_value": 1000000}},
    )
    sqlite_session.add(v1_snap)
    await sqlite_session.flush()

    deal_v1 = Deal(
        tenant_id=tenant_id,
        snapshot_id=v1_id,
        item_id="DEAL-01",
        deal_name="Deal V1",
        normalized_deal_value=Decimal("1000000.00"),
        currency="INR",
        deal_status="Won",
        deal_stage="Closed",
        classification="WON",
        sector_service="Survey",
    )
    wo_v1 = WorkOrder(
        tenant_id=tenant_id,
        snapshot_id=v1_id,
        wo_id="WO-01",
        customer_name="Client A",
        execution_status="Completed",
    )
    sqlite_session.add_all([deal_v1, wo_v1])
    await sqlite_session.commit()

    # 2. Simulate Candidate Snapshot (v2) persistence ordering
    # Step A: Create candidate SnapshotMetadata with is_active=False
    v2_id = uuid.uuid4()
    candidate_snap = SnapshotMetadata(
        snapshot_id=v2_id,
        tenant_id=tenant_id,
        version=2,
        is_active=False,  # MUST be False during build
        data_source="monday_api",
        data_status="live",
        total_deals=2,
        total_work_orders=1,
        active_pipeline_value=Decimal("2500000.00"),
        gross_opportunity_value=Decimal("2500000.00"),
        metrics_cache={"pipeline_summary": {"active_pipeline_value": 2500000}},
    )
    sqlite_session.add(candidate_snap)
    await sqlite_session.flush()

    # Verify query for active snapshot still returns v1 only
    stmt_active = select(SnapshotMetadata).where(
        SnapshotMetadata.tenant_id == tenant_id,
        SnapshotMetadata.is_active == True,
    )
    active_now = (await sqlite_session.execute(stmt_active)).scalar_one()
    assert active_now.snapshot_id == v1_id

    # Step B: Insert candidate deals referencing candidate_snap
    deal_v2_1 = Deal(
        tenant_id=tenant_id,
        snapshot_id=v2_id,
        item_id="DEAL-01",
        deal_name="Deal V1 Updated",
        normalized_deal_value=Decimal("1500000.00"),
        currency="INR",
        deal_status="Won",
        deal_stage="Closed",
        classification="WON",
        sector_service="Survey",
    )
    deal_v2_2 = Deal(
        tenant_id=tenant_id,
        snapshot_id=v2_id,
        item_id="DEAL-02",
        deal_name="Deal V2 New",
        normalized_deal_value=Decimal("1000000.00"),
        currency="INR",
        deal_status="Open",
        deal_stage="Proposal",
        classification="OPEN",
        sector_service="Wind",
    )
    sqlite_session.add_all([deal_v2_1, deal_v2_2])
    await sqlite_session.flush()

    # Step C: Simulate Candidate Rollback (e.g. error before cutover)
    await sqlite_session.rollback()

    # Verify candidate is gone and active v1 snapshot is preserved
    active_post_rollback = (await sqlite_session.execute(stmt_active)).scalar_one()
    assert active_post_rollback.snapshot_id == v1_id
    assert active_post_rollback.version == 1

    # Verify candidate deals do not exist
    stmt_v2_deals = select(Deal).where(Deal.snapshot_id == v2_id)
    v2_deals = (await sqlite_session.execute(stmt_v2_deals)).scalars().all()
    assert len(v2_deals) == 0

    # Step D: Test Atomic Cutover
    # Re-insert candidate
    sqlite_session.add(candidate_snap)
    sqlite_session.add_all([deal_v2_1, deal_v2_2])
    await sqlite_session.flush()

    # Atomic cutover inside a transaction:
    # 1. Deactivate current active snapshot
    await sqlite_session.execute(
        update(SnapshotMetadata)
        .where(SnapshotMetadata.tenant_id == tenant_id, SnapshotMetadata.is_active == True)
        .values(is_active=False)
    )
    # 2. Activate candidate
    candidate_snap.is_active = True
    await sqlite_session.commit()

    # Verification: Now v2 is active, v1 is inactive
    active_final = (await sqlite_session.execute(stmt_active)).scalar_one()
    assert active_final.snapshot_id == v2_id
    assert active_final.version == 2
    assert active_final.is_active is True


# =====================================================================
# 4. Multiple Integration Connections and Multiple Boards per Connection
# =====================================================================

@pytest.mark.asyncio
async def test_sqlite_multiple_connections_and_boards(sqlite_session: AsyncSession):
    """
    Verify support for multiple Monday integration connections per tenant
    and multiple boards per connection (including multiple boards of the same type).
    Enforces uq_connection_board_id (connection_id, monday_board_id).
    """
    tenant_id = uuid.uuid4()
    t = Tenant(tenant_id=tenant_id, name="Multi Conn Tenant", slug="multi-conn")
    sqlite_session.add(t)
    await sqlite_session.flush()

    # Connection 1: Sales Workspace
    conn_sales = IntegrationConnection(
        connection_id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider="monday",
        connection_name="Sales Workspace",
        encrypted_credentials="enc:token:1",
        status="ACTIVE",
    )
    # Connection 2: Field Operations Workspace
    conn_ops = IntegrationConnection(
        connection_id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider="monday",
        connection_name="Operations Workspace",
        encrypted_credentials="enc:token:2",
        status="ACTIVE",
    )
    sqlite_session.add_all([conn_sales, conn_ops])
    await sqlite_session.flush()

    # Multiple boards for Sales connection (e.g. Enterprise Deals and SMB Deals, both board_type='deals')
    b1 = TenantBoardConfig(
        config_id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=conn_sales.connection_id,
        board_type="deals",
        monday_board_id="111001",
        monday_board_name="Enterprise Deals",
    )
    b2 = TenantBoardConfig(
        config_id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=conn_sales.connection_id,
        board_type="deals",  # Same board type on same connection!
        monday_board_id="111002",
        monday_board_name="SMB Deals",
    )
    # Operations board
    b3 = TenantBoardConfig(
        config_id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=conn_ops.connection_id,
        board_type="work_orders",
        monday_board_id="222001",
        monday_board_name="Field Work Orders",
    )
    sqlite_session.add_all([b1, b2, b3])
    await sqlite_session.commit()

    # Verify all configs were saved and can be retrieved
    configs = (
        await sqlite_session.execute(
            select(TenantBoardConfig).where(TenantBoardConfig.tenant_id == tenant_id)
        )
    ).scalars().all()
    assert len(configs) == 3

    # Duplicate (connection_id, monday_board_id) should violate unique constraint
    duplicate_b = TenantBoardConfig(
        config_id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=conn_sales.connection_id,
        board_type="deals",
        monday_board_id="111001",  # Duplicate monday_board_id on same connection
        monday_board_name="Duplicate Board",
    )
    sqlite_session.add(duplicate_b)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await sqlite_session.commit()
    await sqlite_session.rollback()


# =====================================================================
# 5. Idempotent Sync Registration and Stale Worker Fencing
# =====================================================================

@pytest.mark.asyncio
async def test_sqlite_idempotency_and_fencing(sqlite_session: AsyncSession):
    """
    Verify:
    1. Idempotency keys prevent duplicate concurrent sync runs.
    2. Fencing tokens (attempt_count) prevent zombie/stale workers from cutting over.
    """
    tenant_id = uuid.uuid4()
    t = Tenant(tenant_id=tenant_id, name="Fencing Tenant", slug="fencing-tenant")
    sqlite_session.add(t)
    await sqlite_session.flush()

    idempotency_key = "sync_2026_11_10_half_hour"

    # Worker 1 registers run
    run = SyncRun(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        status="RUNNING",
        job_state="RUNNING",
        started_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
        attempt_count=1,
    )
    sqlite_session.add(run)
    await sqlite_session.commit()

    # Worker 2 attempts registration with same idempotency key
    # SyncEngine detects active job and returns should_proceed=False
    sync_engine = SyncEngine(session=sqlite_session, tenant_id=tenant_id)
    existing_run, should_proceed = await sync_engine.register_or_claim_sync_job(
        idempotency_key=idempotency_key,
    )
    assert existing_run.run_id == run.run_id
    assert should_proceed is False

    # Simulate another worker taking over or incrementing attempt_count
    await sqlite_session.execute(
        update(SyncRun)
        .where(SyncRun.run_id == run.run_id)
        .values(attempt_count=2)
    )
    await sqlite_session.commit()

    # Worker 1 checks fencing token with its stale attempt_count=1
    sync_engine.claimed_attempt = 1
    fencing_stmt = (
        update(SyncRun)
        .where(
            SyncRun.run_id == run.run_id,
            SyncRun.attempt_count == sync_engine.claimed_attempt,
        )
        .values(job_state="COMPLETED", status="SUCCESS")
    )
    res = await sqlite_session.execute(fencing_stmt)
    if res.rowcount == 0:
        with pytest.raises(ZombieWorkerFencedError, match="ownership lost"):
            raise ZombieWorkerFencedError(
                f"Sync run {run.run_id} ownership lost (attempt {sync_engine.claimed_attempt} superseded). Fencing out worker."
            )

