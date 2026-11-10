"""
Models package initialization.
Exports all database entity models for metadata registration and Alembic discovery.
"""

from db.models.deal import Deal
from db.models.work_order import WorkOrder
from db.models.snapshot import SnapshotMetadata, SyncRun
from db.models.tenant import (
    Tenant,
    VerifiedDomain,
    User,
    TenantMembership,
    IntegrationConnection,
    TenantBoardConfig,
)

__all__ = [
    "Deal",
    "WorkOrder",
    "SnapshotMetadata",
    "SyncRun",
    "Tenant",
    "VerifiedDomain",
    "User",
    "TenantMembership",
    "IntegrationConnection",
    "TenantBoardConfig",
]
