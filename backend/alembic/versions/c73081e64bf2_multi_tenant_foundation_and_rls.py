"""multi_tenant_foundation_and_rls

Revision ID: c73081e64bf2
Revises: 8185cee60cff
Create Date: 2026-11-10 16:45:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
import db.models.snapshot

# revision identifiers, used by Alembic.
revision: str = 'c73081e64bf2'
down_revision: Union[str, Sequence[str], None] = '8185cee60cff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SKYLARP_TENANT_ID = '11111111-1111-1111-1111-111111111111'


def upgrade() -> None:
    """Upgrade schema to multi-tenant foundation, composite keys, backfill, and RLS."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # =================================================================
    # 1. Create Tenant Identity & Management Tables
    # =================================================================
    op.create_table(
        'tenants',
        sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), primary_key=True),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('subscription_plan', sa.String(length=32), nullable=False, server_default='standard'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('currency_code', sa.String(length=16), nullable=False, server_default='INR'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    op.create_table(
        'verified_domains',
        sa.Column('domain_id', db.models.snapshot.PortableUUID(length=36), primary_key=True),
        sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('domain_name', sa.String(length=255), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('verification_token', sa.String(length=128), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'domain_name', name='uq_tenant_domain'),
    )

    op.create_table(
        'users',
        sa.Column('user_id', db.models.snapshot.PortableUUID(length=36), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'tenant_memberships',
        sa.Column('membership_id', db.models.snapshot.PortableUUID(length=36), primary_key=True),
        sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', db.models.snapshot.PortableUUID(length=36), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='ANALYST'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'user_id', name='uq_tenant_user_membership'),
    )

    op.create_table(
        'integration_connections',
        sa.Column('connection_id', db.models.snapshot.PortableUUID(length=36), primary_key=True),
        sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('connection_name', sa.String(length=128), nullable=False, server_default='Default Connection'),
        sa.Column('provider', sa.String(length=32), nullable=False, server_default='monday'),
        sa.Column('auth_type', sa.String(length=32), nullable=False, server_default='api_token'),
        sa.Column('encrypted_credentials', sa.Text(), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False, server_default='v1'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='ACTIVE'),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'connection_name', name='uq_tenant_connection_name'),
    )

    op.create_table(
        'tenant_board_configs',
        sa.Column('config_id', db.models.snapshot.PortableUUID(length=36), primary_key=True),
        sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('connection_id', db.models.snapshot.PortableUUID(length=36), sa.ForeignKey('integration_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('board_type', sa.String(length=32), nullable=False),
        sa.Column('monday_board_id', sa.String(length=64), nullable=False),
        sa.Column('monday_board_name', sa.String(length=255), nullable=False, server_default='Board'),
        sa.Column('column_mappings', db.models.snapshot.PortableJSON(), nullable=False),
        sa.Column('is_sync_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'board_type', name='uq_tenant_board_type'),
    )

    # =================================================================
    # 2. Seed Default Skylarp Tenant for Backfill
    # =================================================================
    op.execute(
        sa.text(
            f"INSERT INTO tenants (tenant_id, slug, name, subscription_plan, status, currency_code) "
            f"VALUES ('{DEFAULT_SKYLARP_TENANT_ID}', 'skylarp-drones', 'Skylarp Drones Executive', 'enterprise', 'active', 'INR')"
        )
    )

    # =================================================================
    # 3. Add tenant_id to Business Tables, Backfill & Apply Constraints
    # =================================================================

    # --- snapshot_metadata ---
    op.drop_index('uq_active_snapshot_flag', table_name='snapshot_metadata', if_exists=True)
    op.drop_index('ix_snapshot_metadata_version', table_name='snapshot_metadata', if_exists=True)

    with op.batch_alter_table('snapshot_metadata', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), nullable=True))

    op.execute(sa.text(f"UPDATE snapshot_metadata SET tenant_id = '{DEFAULT_SKYLARP_TENANT_ID}' WHERE tenant_id IS NULL"))

    with op.batch_alter_table('snapshot_metadata', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.create_foreign_key('fk_snapshot_metadata_tenant_id', 'tenants', ['tenant_id'], ['tenant_id'], ondelete='CASCADE')
        batch_op.create_unique_constraint('uq_tenant_snapshot_version', ['tenant_id', 'version'])
        batch_op.create_unique_constraint('uq_tenant_snapshot_id', ['tenant_id', 'snapshot_id'])

    op.create_index(
        'uq_tenant_active_snapshot',
        'snapshot_metadata',
        ['tenant_id', 'is_active'],
        unique=True,
        postgresql_where=sa.text('is_active = TRUE'),
    )

    # --- deals ---
    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), nullable=True))

    op.execute(sa.text(f"UPDATE deals SET tenant_id = '{DEFAULT_SKYLARP_TENANT_ID}' WHERE tenant_id IS NULL"))

    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.drop_constraint('fk_deals_snapshot_id_snapshot_metadata', type_='foreignkey')
        batch_op.drop_constraint('pk_deals', type_='primary')
        batch_op.create_primary_key('pk_deals', ['tenant_id', 'snapshot_id', 'item_id'])
        batch_op.create_foreign_key(
            'fk_deals_tenant_snapshot',
            'snapshot_metadata',
            ['tenant_id', 'snapshot_id'],
            ['tenant_id', 'snapshot_id'],
            ondelete='CASCADE',
        )
        batch_op.create_index('ix_deals_tenant_item', ['tenant_id', 'item_id'], unique=False)
        batch_op.create_index('ix_deals_tenant_snapshot', ['tenant_id', 'snapshot_id'], unique=False)
        batch_op.create_index('ix_deals_tenant_classif_val', ['tenant_id', 'snapshot_id', 'classification', 'value_status'], unique=False)
        batch_op.create_index('ix_deals_tenant_sector', ['tenant_id', 'snapshot_id', 'sector_service', 'classification'], unique=False)

    # --- work_orders ---
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), nullable=True))

    op.execute(sa.text(f"UPDATE work_orders SET tenant_id = '{DEFAULT_SKYLARP_TENANT_ID}' WHERE tenant_id IS NULL"))

    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.drop_constraint('fk_work_orders_snapshot_id_snapshot_metadata', type_='foreignkey')
        batch_op.drop_constraint('pk_work_orders', type_='primary')
        batch_op.create_primary_key('pk_work_orders', ['tenant_id', 'snapshot_id', 'wo_id'])
        batch_op.create_foreign_key(
            'fk_work_orders_tenant_snapshot',
            'snapshot_metadata',
            ['tenant_id', 'snapshot_id'],
            ['tenant_id', 'snapshot_id'],
            ondelete='CASCADE',
        )
        batch_op.create_index('ix_work_orders_tenant_wo', ['tenant_id', 'wo_id'], unique=False)
        batch_op.create_index('ix_work_orders_tenant_snapshot', ['tenant_id', 'snapshot_id'], unique=False)
        batch_op.create_index('ix_wo_tenant_customer_status', ['tenant_id', 'snapshot_id', 'customer_name', 'execution_status'], unique=False)

    # --- sync_runs ---
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', db.models.snapshot.PortableUUID(length=36), nullable=True))
        batch_op.add_column(sa.Column('connection_id', db.models.snapshot.PortableUUID(length=36), nullable=True))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('job_state', sa.String(length=32), nullable=False, server_default='QUEUED'))
        batch_op.add_column(sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='1'))

    op.execute(sa.text(f"UPDATE sync_runs SET tenant_id = '{DEFAULT_SKYLARP_TENANT_ID}', idempotency_key = 'bootstrap_legacy_' || run_id WHERE tenant_id IS NULL"))

    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.alter_column('idempotency_key', nullable=False)
        batch_op.create_foreign_key('fk_sync_runs_tenant_id', 'tenants', ['tenant_id'], ['tenant_id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_sync_runs_connection_id', 'integration_connections', ['connection_id'], ['connection_id'], ondelete='SET NULL')
        batch_op.create_unique_constraint('uq_tenant_idempotency_key', ['tenant_id', 'idempotency_key'])
        batch_op.create_index('ix_sync_runs_tenant_started', ['tenant_id', 'started_at'])

    # =================================================================
    # 4. PostgreSQL Row-Level Security (RLS) Policies
    # =================================================================
    if is_postgres:
        tables_to_secure = [
            'snapshot_metadata',
            'deals',
            'work_orders',
            'sync_runs',
            'integration_connections',
            'tenant_board_configs',
        ]
        for tbl in tables_to_secure:
            op.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"))
            op.execute(sa.text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;"))
            op.execute(
                sa.text(
                    f"CREATE POLICY tenant_isolation_{tbl} ON {tbl} "
                    f"FOR ALL "
                    f"USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
                    f"WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);"
                )
            )


def downgrade() -> None:
    """Downgrade schema back to single-tenant Revision 2."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        tables_to_secure = [
            'snapshot_metadata',
            'deals',
            'work_orders',
            'sync_runs',
            'integration_connections',
            'tenant_board_configs',
        ]
        for tbl in tables_to_secure:
            op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl};"))
            op.execute(sa.text(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;"))
            op.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;"))

        # Safely drop PostgreSQL foreign keys that may use naming convention
        op.execute(sa.text("ALTER TABLE sync_runs DROP CONSTRAINT IF EXISTS fk_sync_runs_connection_id;"))
        op.execute(sa.text("ALTER TABLE sync_runs DROP CONSTRAINT IF EXISTS fk_sync_runs_connection_id_integration_connections;"))
        op.execute(sa.text("ALTER TABLE sync_runs DROP CONSTRAINT IF EXISTS fk_sync_runs_tenant_id;"))
        op.execute(sa.text("ALTER TABLE sync_runs DROP CONSTRAINT IF EXISTS fk_sync_runs_tenant_id_tenants;"))
        op.execute(sa.text("ALTER TABLE work_orders DROP CONSTRAINT IF EXISTS fk_work_orders_tenant_snapshot;"))
        op.execute(sa.text("ALTER TABLE work_orders DROP CONSTRAINT IF EXISTS fk_work_orders_tenant_id_snapshot_id_snapshot_metadata;"))
        op.execute(sa.text("ALTER TABLE deals DROP CONSTRAINT IF EXISTS fk_deals_tenant_snapshot;"))
        op.execute(sa.text("ALTER TABLE deals DROP CONSTRAINT IF EXISTS fk_deals_tenant_id_snapshot_id_snapshot_metadata;"))
        op.execute(sa.text("ALTER TABLE snapshot_metadata DROP CONSTRAINT IF EXISTS fk_snapshot_metadata_tenant_id;"))
        op.execute(sa.text("ALTER TABLE snapshot_metadata DROP CONSTRAINT IF EXISTS fk_snapshot_metadata_tenant_id_tenants;"))

    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tenant_idempotency_key', type_='unique')
        if not is_postgres:
            batch_op.drop_constraint('fk_sync_runs_connection_id', type_='foreignkey')
            batch_op.drop_constraint('fk_sync_runs_tenant_id', type_='foreignkey')
        batch_op.drop_index('ix_sync_runs_tenant_started')
        batch_op.drop_column('attempt_count')
        batch_op.drop_column('heartbeat_at')
        batch_op.drop_column('job_state')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('connection_id')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        if not is_postgres:
            batch_op.drop_constraint('fk_work_orders_tenant_snapshot', type_='foreignkey')
        batch_op.drop_constraint('pk_work_orders', type_='primary')
        batch_op.create_primary_key('pk_work_orders', ['snapshot_id', 'wo_id'])
        batch_op.create_foreign_key(
            'fk_work_orders_snapshot_id_snapshot_metadata',
            'snapshot_metadata',
            ['snapshot_id'],
            ['snapshot_id'],
            ondelete='CASCADE',
        )
        batch_op.drop_index('ix_wo_tenant_customer_status')
        batch_op.drop_index('ix_work_orders_tenant_snapshot')
        batch_op.drop_index('ix_work_orders_tenant_wo')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('deals', schema=None) as batch_op:
        if not is_postgres:
            batch_op.drop_constraint('fk_deals_tenant_snapshot', type_='foreignkey')
        batch_op.drop_constraint('pk_deals', type_='primary')
        batch_op.create_primary_key('pk_deals', ['snapshot_id', 'item_id'])
        batch_op.create_foreign_key(
            'fk_deals_snapshot_id_snapshot_metadata',
            'snapshot_metadata',
            ['snapshot_id'],
            ['snapshot_id'],
            ondelete='CASCADE',
        )
        batch_op.drop_index('ix_deals_tenant_sector')
        batch_op.drop_index('ix_deals_tenant_classif_val')
        batch_op.drop_index('ix_deals_tenant_snapshot')
        batch_op.drop_index('ix_deals_tenant_item')
        batch_op.drop_column('tenant_id')

    # Delete non-default tenant snapshots during downgrade to restore single-tenant uniqueness
    op.execute(sa.text(f"DELETE FROM snapshot_metadata WHERE tenant_id != '{DEFAULT_SKYLARP_TENANT_ID}';"))

    op.drop_index('uq_tenant_active_snapshot', table_name='snapshot_metadata', if_exists=True)
    with op.batch_alter_table('snapshot_metadata', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tenant_snapshot_id', type_='unique')
        batch_op.drop_constraint('uq_tenant_snapshot_version', type_='unique')
        if not is_postgres:
            batch_op.drop_constraint('fk_snapshot_metadata_tenant_id', type_='foreignkey')
        batch_op.drop_column('tenant_id')

    op.create_index('ix_snapshot_metadata_version', 'snapshot_metadata', ['version'], unique=True)

    op.create_index(
        'uq_active_snapshot_flag',
        'snapshot_metadata',
        ['is_active'],
        unique=True,
        postgresql_where=sa.text('is_active = TRUE'),
    )

    op.drop_table('tenant_board_configs')
    op.drop_table('integration_connections')
    op.drop_table('tenant_memberships')
    op.drop_table('users')
    op.drop_table('verified_domains')
    op.drop_table('tenants')
