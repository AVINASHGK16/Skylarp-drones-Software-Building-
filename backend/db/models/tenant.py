"""
Multi-Tenant Identity, Organization, Membership, and Integration Models.
"""

from datetime import datetime, timezone
import uuid
from typing import Any
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin
from db.models.snapshot import PortableJSON, PortableUUID


class Tenant(Base, TimestampMixin):
    """
    Organization entity representing an isolated customer tenant.
    """

    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_plan: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        nullable=False,
        comment="'active', 'pending_approval', 'suspended', 'archived'",
    )
    currency_code: Mapped[str] = mapped_column(String(16), default="INR", nullable=False)

    # Relationships
    memberships = relationship("TenantMembership", back_populates="tenant", cascade="all, delete-orphan")
    verified_domains = relationship("VerifiedDomain", back_populates="tenant", cascade="all, delete-orphan")
    integrations = relationship("IntegrationConnection", back_populates="tenant", cascade="all, delete-orphan")
    board_configs = relationship("TenantBoardConfig", back_populates="tenant", cascade="all, delete-orphan")


class VerifiedDomain(Base, TimestampMixin):
    """
    Company domain verified by a tenant (e.g., 'skylarp.com').
    Enables domain-based user validation.
    """

    __tablename__ = "verified_domains"

    domain_id: Mapped[uuid.UUID] = mapped_column(
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
    domain_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="verified_domains")

    __table_args__ = (
        UniqueConstraint("tenant_id", "domain_name", name="uq_tenant_domain"),
    )


class User(Base, TimestampMixin):
    """
    Global user identity. A user may hold memberships across multiple tenants.
    """

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships = relationship("TenantMembership", back_populates="user", cascade="all, delete-orphan")


class TenantMembership(Base, TimestampMixin):
    """
    Role-Based Access Control link between a User and a Tenant.
    Roles: 'OWNER', 'ADMIN', 'EXECUTIVE', 'ANALYST'.
    """

    __tablename__ = "tenant_memberships"

    membership_id: Mapped[uuid.UUID] = mapped_column(
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
    user_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        default="ANALYST",
        nullable=False,
        comment="'OWNER', 'ADMIN', 'EXECUTIVE', 'ANALYST'",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tenant = relationship("Tenant", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user_membership"),
        Index("ix_tenant_memberships_tenant_user", "tenant_id", "user_id"),
    )


class IntegrationConnection(Base, TimestampMixin):
    """
    Encrypted Monday.com integration credentials and connection metadata.
    """

    __tablename__ = "integration_connections"

    connection_id: Mapped[uuid.UUID] = mapped_column(
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
    connection_name: Mapped[str] = mapped_column(String(128), default="Default Connection", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="monday", nullable=False)
    auth_type: Mapped[str] = mapped_column(String(32), default="api_token", nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(64), default="v1", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
        comment="'ACTIVE', 'INVALID_CREDENTIALS', 'RATE_LIMITED', 'DISABLED'",
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="integrations")
    board_configs = relationship("TenantBoardConfig", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "connection_name", name="uq_tenant_connection_name"),
    )


class TenantBoardConfig(Base, TimestampMixin):
    """
    Board-level and column mapping configurations for a tenant's integration.
    """

    __tablename__ = "tenant_board_configs"

    config_id: Mapped[uuid.UUID] = mapped_column(
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
    connection_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID,
        ForeignKey("integration_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    board_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="'deals' or 'work_orders'",
    )
    monday_board_id: Mapped[str] = mapped_column(String(64), nullable=False)
    monday_board_name: Mapped[str] = mapped_column(String(255), default="Board", nullable=False)
    column_mappings: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON,
        nullable=False,
        default=dict,
        comment="Maps Monday column IDs to canonical domain keys",
    )
    is_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tenant = relationship("Tenant", back_populates="board_configs")
    connection = relationship("IntegrationConnection", back_populates="board_configs")

    __table_args__ = (
        UniqueConstraint("connection_id", "monday_board_id", name="uq_connection_board_id"),
    )

