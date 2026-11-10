"""
WorkOrder Model for Multi-Tenant PostgreSQL storage.
Preserves operational delivery metrics, realization backlog, and exact NUMERIC contracts.
Scoped to Tenant and Snapshot via composite primary key (tenant_id, snapshot_id, wo_id)
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


class WorkOrder(Base, TimestampMixin):
    """
    Durable, tenant-isolated representation of an operational Work Order.
    Tracks execution fulfillment and financial billing realization.
    Composite primary key (tenant_id, snapshot_id, wo_id) and composite foreign
    key ensure cross-tenant isolation at the database constraint level.
    """

    __tablename__ = "work_orders"

    # Multi-Tenant Composite Primary Key
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        nullable=False,
        comment="Tenant organization owning this work order",
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        nullable=False,
        comment="Snapshot generation that owns this immutable work order record",
    )
    wo_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        nullable=False,
        comment="Stable source work order identifier from Monday.com",
    )

    customer_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    
    # Categorical delivery execution
    raw_execution_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Unknown",
        index=True,
        comment="'Completed', 'Ongoing', 'Pause / Struck', 'Not Started', etc.",
    )

    # Financial Values (NUMERIC(18, 2) exact precision in INR)
    raw_contract_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_contract_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    raw_billed_amount: Mapped[str | None] = mapped_column(String(128), nullable=True)
    billed_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    unbilled_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    value_status: Mapped[str] = mapped_column(
        String(32),
        default="VALID",
        nullable=False,
    )

    # Operational Dates
    po_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    probable_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    probable_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Tombstone Management within Snapshot
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["snapshot_metadata.tenant_id", "snapshot_metadata.snapshot_id"],
            name="fk_work_orders_tenant_snapshot",
            ondelete="CASCADE",
        ),
        Index("ix_work_orders_tenant_wo", "tenant_id", "wo_id"),
        Index("ix_work_orders_tenant_snapshot", "tenant_id", "snapshot_id"),
        Index("ix_wo_tenant_customer_status", "tenant_id", "snapshot_id", "customer_name", "execution_status"),
    )
