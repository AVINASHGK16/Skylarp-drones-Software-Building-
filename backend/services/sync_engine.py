"""
Idempotent Multi-Tenant Synchronization and Immutable Snapshot Pipeline Engine.

Implements:
1. Pinned Session-Level PostgreSQL Advisory Locking scoped to (tenant_id, connection_id).
2. Idempotent Job Lifecycle Management (QUEUED, RUNNING, VALIDATING, COMMITTING, COMPLETED, FAILED).
3. Stale Job Recovery with Distributed Fencing Tokens (attempt_count).
4. Complete 15-Step Immutable Snapshot Pipeline with Explicit In-Memory vs DB Write Boundaries.
5. Atomic In-Transaction Snapshot Cutover.
6. Multi-Connection & Multi-Board Configuration Management.
7. Tenant-Scoped Historical Snapshot Retention Pruning.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import logging
import struct
from typing import Any
import uuid
import pandas as pd
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from db.models.deal import Deal
from db.models.snapshot import SnapshotMetadata, SyncRun
from db.models.tenant import IntegrationConnection, TenantBoardConfig
from db.models.work_order import WorkOrder
from services.analytics_engine import generate_dashboard_metrics
from services.crypto_service import decrypt_credentials
from services.data_cleaner import (
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)

logger = logging.getLogger(__name__)

# Fallback lock dictionary for SQLite / Non-PostgreSQL dialect runs
_sqlite_locks: dict[str, asyncio.Lock] = {}
_sqlite_master_lock = asyncio.Lock()


class AdvisoryLockAcquisitionError(Exception):
    """Raised when an advisory lock cannot be acquired due to active concurrent synchronization."""
    pass


class SnapshotValidationError(Exception):
    """Raised when candidate records fail validation before snapshot activation."""
    pass


class ZombieWorkerFencedError(Exception):
    """Raised when a worker's ownership of a sync run was superseded by stale job recovery."""
    pass


def compute_advisory_lock_key_64(tenant_id: uuid.UUID, connection_id: uuid.UUID | None = None) -> int:
    """
    Generate a collision-resistant 64-bit signed integer key from (tenant_id, connection_id)
    for PostgreSQL advisory locking.
    Uses SHA-256 truncated to 8 bytes and unpacked as a big-endian signed 64-bit integer (-2^63 to 2^63 - 1).
    Collision resistance: ~5.06 x 10^9 keys for 50% collision probability, compared to only ~77,000 keys for 32-bit hashtext.
    """
    conn_id = connection_id or uuid.UUID("00000000-0000-0000-0000-000000000000")
    key_str = f"{tenant_id}:{conn_id}"
    digest = hashlib.sha256(key_str.encode("utf-8")).digest()
    return struct.unpack(">q", digest[:8])[0]


class SessionAdvisoryLock:
    """
    Session-level PostgreSQL advisory lock pinned to a single database connection.
    Scoped strictly to (tenant_id, connection_id).
    
    Guarantees:
    - Held by the database session (connection), not a transaction.
    - Uses 64-bit SHA-256 collision-resistant key strategy.
    - Verifies explicit unlock success before returning connection to pool.
    - Invalidates connection on unlock or connection health failure to prevent pool poisoning.
    - No long-running database transactions across network calls.
    - Reliable cleanup in finally blocks.
    - Independent connections for the same tenant sync in parallel.
    - Connection loss automatically drops the lock in PostgreSQL.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID | None = None,
    ):
        self.engine = engine
        self.tenant_id = tenant_id
        self.connection_id = connection_id or uuid.UUID("00000000-0000-0000-0000-000000000000")
        self.lock_key = f"{self.tenant_id}:{self.connection_id}"
        self.lock_key_64 = compute_advisory_lock_key_64(self.tenant_id, self.connection_id)
        self.conn: AsyncConnection | None = None
        self.is_locked = False

    async def acquire(self) -> bool:
        """Acquire session-level advisory lock on a pinned database connection."""
        self.conn = await self.engine.connect()
        bind_dialect = self.engine.dialect.name

        if bind_dialect == "postgresql":
            res = await self.conn.execute(
                text("SELECT pg_try_advisory_lock(CAST(:key AS BIGINT))"),
                {"key": self.lock_key_64},
            )
            self.is_locked = bool(res.scalar_one())
            if not self.is_locked:
                await self.conn.close()
                self.conn = None
            return self.is_locked
        else:
            # Asyncio lock for SQLite / in-memory testing
            async with _sqlite_master_lock:
                if self.lock_key not in _sqlite_locks:
                    _sqlite_locks[self.lock_key] = asyncio.Lock()
                lock = _sqlite_locks[self.lock_key]

            if lock.locked():
                await self.conn.close()
                self.conn = None
                self.is_locked = False
                return False

            await lock.acquire()
            self.is_locked = True
            return True

    async def release(self) -> None:
        """Release session-level advisory lock and return/invalidate pinned connection."""
        if not self.is_locked:
            if self.conn:
                await self.conn.close()
                self.conn = None
            return

        should_invalidate = False
        try:
            if self.engine.dialect.name == "postgresql" and self.conn:
                res = await self.conn.execute(
                    text("SELECT pg_advisory_unlock(CAST(:key AS BIGINT))"),
                    {"key": self.lock_key_64},
                )
                unlocked = bool(res.scalar_one())
                if not unlocked:
                    logger.warning(
                        "Advisory lock %s (64-bit key %s) was not held by session or failed to unlock cleanly",
                        self.lock_key,
                        self.lock_key_64,
                    )
                    should_invalidate = True
            elif self.engine.dialect.name != "postgresql":
                async with _sqlite_master_lock:
                    lock = _sqlite_locks.get(self.lock_key)
                    if lock and lock.locked():
                        lock.release()
        except Exception as e:
            logger.warning("Error releasing advisory lock %s (64-bit key %s): %s", self.lock_key, self.lock_key_64, e)
            should_invalidate = True
        finally:
            self.is_locked = False
            if self.conn:
                if should_invalidate:
                    try:
                        await self.conn.invalidate()
                    except Exception as inv_err:
                        logger.warning("Failed to invalidate connection: %s", inv_err)
                else:
                    await self.conn.close()
                self.conn = None

    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise AdvisoryLockAcquisitionError(
                f"Concurrent synchronization already active for tenant {self.tenant_id} connection {self.connection_id}."
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


async def get_advisory_lock(session: AsyncSession, tenant_id: uuid.UUID, connection_id: uuid.UUID | None) -> bool:
    """Helper for testing session-level advisory lock acquisition."""
    bind = session.bind
    is_postgres = bind and bind.dialect.name == "postgresql"
    lock_key_str = f"{tenant_id}:{connection_id or '00000000-0000-0000-0000-000000000000'}"

    if is_postgres:
        key_64 = compute_advisory_lock_key_64(tenant_id, connection_id)
        res = await session.execute(
            text("SELECT pg_try_advisory_lock(CAST(:key AS BIGINT))"),
            {"key": key_64},
        )
        acquired = bool(res.scalar_one())
        if acquired:
            # Unlock to leave clean test state
            await session.execute(
                text("SELECT pg_advisory_unlock(CAST(:key AS BIGINT))"),
                {"key": key_64},
            )
        return acquired
    else:
        async with _sqlite_master_lock:
            if lock_key_str not in _sqlite_locks:
                _sqlite_locks[lock_key_str] = asyncio.Lock()
            lock = _sqlite_locks[lock_key_str]
        return not lock.locked()


class SyncEngine:
    """
    Orchestrates idempotent ingestion, candidate record staging, atomic publication,
    and historical snapshot retention for a specific tenant and connection.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID | None = None,
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.connection_id = connection_id
        self.claimed_attempt = 1

    async def get_connection_credentials(self) -> str:
        """Retrieve and decrypt credentials for the authorized connection."""
        if not self.connection_id:
            raise ValueError("No connection_id configured on this SyncEngine instance")

        stmt = select(IntegrationConnection).where(
            IntegrationConnection.connection_id == self.connection_id,
            IntegrationConnection.tenant_id == self.tenant_id,
            IntegrationConnection.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        conn = res.scalar_one_or_none()
        if not conn:
            raise ValueError(f"Active connection {self.connection_id} not found for tenant {self.tenant_id}")

        return decrypt_credentials(conn.encrypted_credentials)

    async def get_board_configs(self, board_type: str | None = None) -> list[TenantBoardConfig]:
        """Retrieve board configurations for this tenant's connection."""
        if not self.connection_id:
            return []

        stmt = select(TenantBoardConfig).where(
            TenantBoardConfig.tenant_id == self.tenant_id,
            TenantBoardConfig.connection_id == self.connection_id,
            TenantBoardConfig.is_sync_enabled == True,
        )
        if board_type:
            stmt = stmt.where(TenantBoardConfig.board_type == board_type)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def register_or_claim_sync_job(
        self,
        idempotency_key: str,
        connection_id: uuid.UUID | None = None,
        source: str = "monday_api",
        stale_timeout_seconds: int = 300,
    ) -> tuple[SyncRun, bool]:
        """
        Idempotently claims or recovers a synchronization job.
        Returns (SyncRun, should_proceed).
        """
        target_conn_id = connection_id or self.connection_id
        now = datetime.now(timezone.utc)
        stmt = select(SyncRun).where(
            SyncRun.tenant_id == self.tenant_id,
            SyncRun.idempotency_key == idempotency_key,
        )
        res = await self.session.execute(stmt)
        existing_job = res.scalar_one_or_none()

        if existing_job:
            # 1. Existing COMPLETED job -> return existing result without re-executing
            if existing_job.job_state == "COMPLETED":
                logger.info("Sync job %s is already COMPLETED. Returning existing result.", idempotency_key)
                return existing_job, False

            # 2. Existing active job (RUNNING, VALIDATING, COMMITTING) -> check for stale heartbeat
            if existing_job.job_state in ["RUNNING", "VALIDATING", "COMMITTING"]:
                age = (now - (existing_job.heartbeat_at or existing_job.started_at)).total_seconds()
                if age < stale_timeout_seconds:
                    logger.warning("Sync job %s is currently active (idle: %.1fs). Skipping.", idempotency_key, age)
                    return existing_job, False

                # Stale job recovery: increment attempt_count to fence out crashed/zombie worker
                logger.warning("Recovering crashed/stale sync job %s (idle: %.1fs)", idempotency_key, age)
                existing_job.attempt_count += 1
                existing_job.heartbeat_at = now
                existing_job.job_state = "RUNNING"
                existing_job.status = "RUNNING"
                await self.session.flush()
                self.claimed_attempt = existing_job.attempt_count
                return existing_job, True

            # 3. Existing FAILED job -> allow controlled retry
            if existing_job.job_state == "FAILED":
                logger.info("Retrying failed sync job %s (attempt %d)", idempotency_key, existing_job.attempt_count + 1)
                existing_job.attempt_count += 1
                existing_job.job_state = "RUNNING"
                existing_job.status = "RUNNING"
                existing_job.heartbeat_at = now
                existing_job.started_at = now
                existing_job.finished_at = None
                existing_job.error_code = None
                existing_job.error_details = None
                await self.session.flush()
                self.claimed_attempt = existing_job.attempt_count
                return existing_job, True

        # 4. New job registration
        new_job = SyncRun(
            tenant_id=self.tenant_id,
            connection_id=target_conn_id,
            idempotency_key=idempotency_key,
            job_state="RUNNING",
            status="RUNNING",
            source=source,
            started_at=now,
            heartbeat_at=now,
            attempt_count=1,
        )
        self.session.add(new_job)
        await self.session.flush()
        self.claimed_attempt = 1
        return new_job, True

    async def execute_candidate_snapshot_pipeline(
        self,
        sync_job: SyncRun,
        raw_deals_data: list[dict[str, Any]],
        raw_work_orders_data: list[dict[str, Any]],
        source_name: str = "monday_api",
        data_status: str = "live",
        column_mappings: dict[str, Any] | None = None,
        retention_keep_count: int = 10,
    ) -> SnapshotMetadata:
        """
        Executes the 15-step immutable candidate snapshot pipeline with explicit
        in-memory validation and atomic database writes.
        """
        candidate_snapshot_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # [DB Write] Step 1: Update sync job state to VALIDATING
        sync_job.job_state = "VALIDATING"
        sync_job.records_fetched = len(raw_deals_data) + len(raw_work_orders_data)
        sync_job.heartbeat_at = now
        await self.session.flush()

        # [In-Memory] Step 2: Clean and normalize source records
        df_deals = clean_deals_data(raw_deals_data)
        df_work_orders = clean_work_orders_data(raw_work_orders_data)

        # [In-Memory] Step 3: Generate data quality report
        quality_report = generate_data_quality_report(df_deals, df_work_orders)

        # [In-Memory] Step 4: Validate business invariants
        if len(df_deals) == 0 and len(df_work_orders) == 0 and (len(raw_deals_data) > 0 or len(raw_work_orders_data) > 0):
            raise SnapshotValidationError("Failed to stage any valid records from non-empty raw inputs")

        # [In-Memory] Step 5: Compute deterministic dashboard metrics
        metrics = generate_dashboard_metrics(df_deals, df_work_orders)
        pipeline_summary = metrics.get("pipeline_summary", {})
        gross_val = Decimal(str(pipeline_summary.get("gross_historical_opportunity_value", 0.0))).quantize(Decimal("0.01"))
        active_val = Decimal(str(pipeline_summary.get("active_pipeline_value", 0.0))).quantize(Decimal("0.01"))

        # [DB Read] Step 6: Determine next tenant monotonic version
        v_res = await self.session.execute(
            select(func.coalesce(func.max(SnapshotMetadata.version), 0))
            .where(SnapshotMetadata.tenant_id == self.tenant_id)
        )
        next_version = v_res.scalar_one() + 1

        # [DB Write] Step 7: Create candidate SnapshotMetadata with is_active = False
        candidate_snapshot = SnapshotMetadata(
            snapshot_id=candidate_snapshot_id,
            tenant_id=self.tenant_id,
            version=next_version,
            is_active=False,  # Safety guarantee: candidate records are never exposed as active
            data_source=source_name,
            data_status=data_status,
            total_deals=len(df_deals),
            total_work_orders=len(df_work_orders),
            active_pipeline_value=active_val,
            gross_opportunity_value=gross_val,
            metrics_cache=metrics,
            quality_report_cache=quality_report,
        )
        self.session.add(candidate_snapshot)
        # Flush candidate metadata FIRST so child tables can reference (tenant_id, candidate_snapshot_id)
        await self.session.flush()

        # [In-Memory Mapping & DB Write] Step 8: Stage Deals
        staged_deals = []
        for _, row in df_deals.iterrows():
            item_id = str(row.get("id", ""))
            if not item_id:
                continue

            num_val = row.get("Masked Deal value")
            decimal_val = None
            if pd.notna(num_val) and num_val is not None:
                try:
                    decimal_val = Decimal(str(num_val)).quantize(Decimal("0.01"))
                except Exception:
                    decimal_val = None

            val_status = str(row.get("Masked Deal value_status", "VALID"))
            if decimal_val is None and val_status == "VALID":
                val_status = "MISSING"

            deal_obj = Deal(
                tenant_id=self.tenant_id,
                snapshot_id=candidate_snapshot_id,
                item_id=item_id,
                deal_name=str(row.get("name", "Untitled Deal")),
                raw_deal_value=str(row.get("Masked Deal value_raw")) if pd.notna(row.get("Masked Deal value_raw")) else None,
                normalized_deal_value=decimal_val,
                value_status=val_status,
                currency="INR",
                raw_deal_status=str(row.get("Deal Status")) if pd.notna(row.get("Deal Status")) else None,
                deal_status=str(row.get("Deal Status", "Unspecified")),
                raw_deal_stage=str(row.get("Deal Stage")) if pd.notna(row.get("Deal Stage")) else None,
                deal_stage=str(row.get("Deal Stage", "Unspecified")),
                classification=str(row.get("Classification", "UNKNOWN_OR_UNCLASSIFIED")),
                classification_reason=str(row.get("Classification Reason", "")),
                sector_service=str(row.get("Sector/service", "Unspecified")),
                close_date=row["Close Date (A)"].date() if pd.notna(row.get("Close Date (A)")) and hasattr(row.get("Close Date (A)"), "date") else None,
                tentative_close_date=row["Tentative Close Date"].date() if pd.notna(row.get("Tentative Close Date")) and hasattr(row.get("Tentative Close Date"), "date") else None,
                created_date=row["Created Date"].date() if pd.notna(row.get("Created Date")) and hasattr(row.get("Created Date"), "date") else None,
            )
            staged_deals.append(deal_obj)

        # [In-Memory Mapping & DB Write] Step 9: Stage Work Orders
        staged_work_orders = []
        for _, row in df_work_orders.iterrows():
            wo_id = str(row.get("id", ""))
            if not wo_id:
                continue

            def to_dec(field_name: str) -> Decimal:
                v = row.get(field_name)
                if pd.notna(v) and v is not None:
                    try:
                        return Decimal(str(v)).quantize(Decimal("0.01"))
                    except Exception:
                        return Decimal("0.00")
                return Decimal("0.00")

            wo_obj = WorkOrder(
                tenant_id=self.tenant_id,
                snapshot_id=candidate_snapshot_id,
                wo_id=wo_id,
                customer_name=str(row.get("Customer Name", "Unknown")),
                raw_execution_status=str(row.get("Execution Status")) if pd.notna(row.get("Execution Status")) else None,
                execution_status=str(row.get("Execution Status", "Unknown")),
                total_contract_value=to_dec("Total Contract Value"),
                billed_amount=to_dec("Billed Amount"),
                unbilled_amount=to_dec("Unbilled Amount"),
                value_status="VALID",
            )
            staged_work_orders.append(wo_obj)

        self.session.add_all(staged_deals)
        self.session.add_all(staged_work_orders)
        await self.session.flush()

        # [DB Write & Fencing Check] Step 10: Verify worker ownership hasn't been superseded
        fencing_stmt = (
            update(SyncRun)
            .where(
                SyncRun.run_id == sync_job.run_id,
                SyncRun.attempt_count == self.claimed_attempt,
                SyncRun.job_state.in_(["RUNNING", "VALIDATING"]),
            )
            .values(job_state="COMMITTING", heartbeat_at=datetime.now(timezone.utc))
        )
        fencing_res = await self.session.execute(fencing_stmt)
        if fencing_res.rowcount == 0:
            raise ZombieWorkerFencedError(
                f"Sync run {sync_job.run_id} ownership lost (attempt {self.claimed_attempt} superseded). Fencing out worker."
            )

        # [DB Write] Step 11: Atomic In-Transaction Cutover
        # Deactivate previous active snapshot for this tenant
        await self.session.execute(
            update(SnapshotMetadata)
            .where(
                SnapshotMetadata.tenant_id == self.tenant_id,
                SnapshotMetadata.is_active == True,
            )
            .values(is_active=False)
        )
        # Activate candidate snapshot
        candidate_snapshot.is_active = True
        await self.session.flush()

        # [DB Write] Step 12: Mark sync run complete
        sync_job.snapshot_id = candidate_snapshot_id
        sync_job.records_staged = len(staged_deals) + len(staged_work_orders)
        sync_job.job_state = "COMPLETED"
        sync_job.status = "SUCCESS"
        sync_job.finished_at = datetime.now(timezone.utc)
        await self.session.flush()

        # [DB Write] Step 13: Retention Pruning (never deletes active snapshots)
        await self._prune_historical_snapshots(retention_keep_count)

        return candidate_snapshot

    async def _prune_historical_snapshots(self, keep_count: int) -> int:
        """
        Prunes older snapshots beyond retention limit for this tenant.
        Guarantees that active snapshots and latest N snapshots are never deleted.
        """
        subq = (
            select(SnapshotMetadata.snapshot_id)
            .where(
                SnapshotMetadata.tenant_id == self.tenant_id,
                SnapshotMetadata.is_active == False,
            )
            .order_by(SnapshotMetadata.version.desc())
            .offset(keep_count)
        )
        old_ids_res = await self.session.execute(subq)
        old_snapshot_ids = old_ids_res.scalars().all()

        if not old_snapshot_ids:
            return 0

        # Unlink foreign key in sync_runs
        await self.session.execute(
            update(SyncRun)
            .where(
                SyncRun.tenant_id == self.tenant_id,
                SyncRun.snapshot_id.in_(old_snapshot_ids),
            )
            .values(snapshot_id=None)
        )

        # Deleting snapshot cascades to owned deals and work orders
        del_stmt = delete(SnapshotMetadata).where(
            SnapshotMetadata.tenant_id == self.tenant_id,
            SnapshotMetadata.snapshot_id.in_(old_snapshot_ids),
            SnapshotMetadata.is_active == False,  # Safety guarantee: never delete active
        )
        res = await self.session.execute(del_stmt)
        pruned_count = res.rowcount
        logger.info("Pruned %d historical snapshots for tenant %s", pruned_count, self.tenant_id)
        return pruned_count
