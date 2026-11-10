"""
SnapshotMetadata and SyncRun models.
Enforces multi-tenant scoping, monotonic versioning per tenant,
single-active snapshot constraint per tenant, and idempotent sync run audit logging.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import JSON, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, TimestampMixin


class PortableUUID(TypeDecorator):
    """Platform-independent UUID type (uses PG UUID natively, CHAR(36) on SQLite)."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        return uuid.UUID(value) if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class PortableJSON(TypeDecorator):
    """Platform-independent JSON type (uses PostgreSQL JSONB natively, standard JSON on SQLite)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB)
        return dialect.type_descriptor(JSON)


class SnapshotMetadata(Base, TimestampMixin):
    """
    Catalog of committed analytical snapshots.
    Scoped to an individual Tenant. Guarantees that each tenant has
    at most one snapshot marked 'is_active = True' at any time.
    """

    __tablename__ = "snapshot_metadata"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Tenant-scoped monotonically increasing integer version (1, 2, 3...)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Flag indicating if this snapshot is the currently active serving snapshot for the tenant",
    )
    data_source: Mapped[str] = mapped_column(
        String(32),
        default="monday_api",
        nullable=False,
        comment="'monday_api', 'excel_bootstrap', or 'manual_import'",
    )
    data_status: Mapped[str] = mapped_column(
        String(32),
        default="live",
        nullable=False,
        comment="'live', 'fallback', or 'degraded'",
    )

    # Summary record metrics
    total_deals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_work_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Financial validation aggregates (exact NUMERIC(18, 2))
    active_pipeline_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    gross_opportunity_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    # Complete serialized dashboard_metrics dictionary
    metrics_cache: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON,
        nullable=False,
        default=dict,
        comment="Complete serialized dashboard_metrics dictionary",
    )

    # Quality and provenance metadata
    quality_report_cache: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON,
        nullable=True,
        default=dict,
    )
    fallback_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        # Tenant-scoped monotonic version uniqueness
        UniqueConstraint("tenant_id", "version", name="uq_tenant_snapshot_version"),
        # Target for child composite foreign keys
        UniqueConstraint("tenant_id", "snapshot_id", name="uq_tenant_snapshot_id"),
        # Unique partial index: At most one active snapshot per tenant
        Index(
            "uq_tenant_active_snapshot",
            "tenant_id",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = TRUE"),
            sqlite_where=text("is_active = 1"),
        ),
        Index("ix_snapshot_tenant_created", "tenant_id", "created_at"),
    )


class SyncRun(Base):
    """
    Audit log and durable job lifecycle record for synchronizations.
    Enforces idempotency by (tenant_id, idempotency_key).
    """

    __tablename__ = "sync_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PortableUUID,
        ForeignKey("integration_connections.connection_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Deterministic key ensuring sync requests are processed idempotently",
    )
    job_state: Mapped[str] = mapped_column(
        String(32),
        default="QUEUED",
        nullable=False,
        comment="'QUEUED', 'RUNNING', 'VALIDATING', 'COMMITTING', 'COMPLETED', 'FAILED'",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="RUNNING",
        nullable=False,
        comment="'SUCCESS', 'FAILED', 'REJECTED_INVALID_DATA', 'SKIPPED_LOCK'",
    )
    source: Mapped[str] = mapped_column(
        String(32),
        default="monday_api",
        nullable=False,
        comment="'monday_api' or 'excel_fallback'",
    )
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_staged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        PortableUUID,
        ForeignKey("snapshot_metadata.snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency_key"),
        Index("ix_sync_runs_tenant_started", "tenant_id", "started_at"),
    )
