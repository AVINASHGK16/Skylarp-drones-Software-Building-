"""
Deal Model for Multi-Tenant PostgreSQL storage.
Preserves both raw source values and cleaned normalized metrics with NUMERIC(18, 2) accuracy.
Scoped to Tenant and Snapshot via composite primary key (tenant_id, snapshot_id, item_id)
and composite foreign key (tenant_id, snapshot_id).
"""

from datetime import date
from decimal import Decimal
import uuid
from sqlalchemy import (
    Boolean,
    Date,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, TimestampMixin
from db.models.snapshot import PortableUUID


class Deal(Base, TimestampMixin):
    """
    Durable, tenant-isolated and snapshot-scoped representation of a deal.
    Composite primary key (tenant_id, snapshot_id, item_id) and composite foreign
    key ensure mathematical isolation: a tenant's records can never point to another
    tenant's snapshots.
    """

    __tablename__ = "deals"

    # Multi-Tenant Composite Primary Key
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        nullable=False,
        comment="Tenant organization owning this deal record",
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        nullable=False,
        comment="Snapshot generation that owns this immutable deal record",
    )
    item_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        nullable=False,
        comment="Stable source item identifier from Monday.com",
    )

    deal_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 1. Financial value preservation: Raw source input vs exact normalized NUMERIC
    raw_deal_value: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Original unparsed string from source (e.g. '₹5,00,000', '1.5 Cr')",
    )
    normalized_deal_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Normalized numeric value in base units. NULL if missing or invalid.",
    )
    value_status: Mapped[str] = mapped_column(
        String(32),
        default="VALID",
        nullable=False,
        comment="'VALID', 'MISSING', 'INVALID', 'UNSUPPORTED_CURRENCY'",
    )
    currency: Mapped[str] = mapped_column(
        String(16),
        default="INR",
        nullable=False,
        comment="Confirmed currency code (e.g., 'INR', 'USD')",
    )

    # 2. Categorical & Operational Statuses: Raw vs Normalized
    raw_deal_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deal_status: Mapped[str] = mapped_column(String(64), nullable=False, default="Unspecified")
    
    raw_deal_stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deal_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="Unspecified")

    classification: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="'WON', 'LOST', 'OPEN', 'DEAD_OR_ABANDONED', 'ON_HOLD', 'UNASSIGNED_INBOUND', 'UNKNOWN_OR_UNCLASSIFIED'",
    )
    classification_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector_service: Mapped[str] = mapped_column(String(128), default="Unspecified", nullable=False)

    # 3. Normalized Dates
    close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tentative_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # 4. Tombstone Management within Snapshot
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Tombstone flag to prevent accidental record loss within this snapshot generation",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["snapshot_metadata.tenant_id", "snapshot_metadata.snapshot_id"],
            name="fk_deals_tenant_snapshot",
            ondelete="CASCADE",
        ),
        Index("ix_deals_tenant_item", "tenant_id", "item_id"),
        Index("ix_deals_tenant_snapshot", "tenant_id", "snapshot_id"),
        Index("ix_deals_tenant_classif_val", "tenant_id", "snapshot_id", "classification", "value_status"),
        Index("ix_deals_tenant_sector", "tenant_id", "snapshot_id", "sector_service", "classification"),
    )
