"""snapshot_scoped_composite_pks_and_rename

Revision ID: 8185cee60cff
Revises: 418a1a68bcfb
Create Date: 2026-11-10 15:04:08.458864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import db.models.snapshot


# revision identifiers, used by Alembic.
revision: str = '8185cee60cff'
down_revision: Union[str, Sequence[str], None] = '418a1a68bcfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to snapshot-scoped composite primary keys and normalized_deal_value."""
    # 1. Drop old indexes before modifying table schema
    op.drop_index('ix_deals_last_seen_snapshot_id', table_name='deals', if_exists=True)
    op.drop_index('ix_deals_classification_status', table_name='deals', if_exists=True)
    op.drop_index('ix_deals_sector_classification', table_name='deals', if_exists=True)
    op.drop_index('ix_work_orders_last_seen_snapshot_id', table_name='work_orders', if_exists=True)
    op.drop_index('ix_wo_customer_status', table_name='work_orders', if_exists=True)

    # 2. Modify deals table with batch_alter_table
    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'snapshot_id',
                db.models.snapshot.PortableUUID(length=36),
                nullable=False,
                comment='Snapshot generation that owns this immutable deal record',
            )
        )
        batch_op.add_column(
            sa.Column(
                'normalized_deal_value',
                sa.Numeric(precision=18, scale=2),
                nullable=True,
                comment='Normalized numeric value in base units. NULL if missing or invalid.',
            )
        )
        batch_op.drop_constraint('fk_deals_last_seen_snapshot_id_snapshot_metadata', type_='foreignkey')
        batch_op.drop_column('masked_deal_value')
        batch_op.drop_column('last_seen_snapshot_id')
        batch_op.create_foreign_key(
            'fk_deals_snapshot_id_snapshot_metadata',
            'snapshot_metadata',
            ['snapshot_id'],
            ['snapshot_id'],
            ondelete='CASCADE',
        )
        batch_op.drop_constraint('pk_deals', type_='primary')
        batch_op.create_primary_key('pk_deals', ['snapshot_id', 'item_id'])
        batch_op.create_index('ix_deals_item_id', ['item_id'], unique=False)
        batch_op.create_index('ix_deals_snapshot_id', ['snapshot_id'], unique=False)
        batch_op.create_index('ix_deals_classification_status', ['snapshot_id', 'classification', 'value_status'], unique=False)
        batch_op.create_index('ix_deals_sector_classification', ['snapshot_id', 'sector_service', 'classification'], unique=False)

    # 3. Modify work_orders table with batch_alter_table
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'snapshot_id',
                db.models.snapshot.PortableUUID(length=36),
                nullable=False,
                comment='Snapshot generation that owns this immutable work order record',
            )
        )
        batch_op.drop_constraint('fk_work_orders_last_seen_snapshot_id_snapshot_metadata', type_='foreignkey')
        batch_op.drop_column('last_seen_snapshot_id')
        batch_op.create_foreign_key(
            'fk_work_orders_snapshot_id_snapshot_metadata',
            'snapshot_metadata',
            ['snapshot_id'],
            ['snapshot_id'],
            ondelete='CASCADE',
        )
        batch_op.drop_constraint('pk_work_orders', type_='primary')
        batch_op.create_primary_key('pk_work_orders', ['snapshot_id', 'wo_id'])
        batch_op.create_index('ix_work_orders_wo_id', ['wo_id'], unique=False)
        batch_op.create_index('ix_work_orders_snapshot_id', ['snapshot_id'], unique=False)
        batch_op.create_index('ix_wo_customer_status', ['snapshot_id', 'customer_name', 'execution_status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_deals_item_id', table_name='deals', if_exists=True)
    op.drop_index('ix_deals_snapshot_id', table_name='deals', if_exists=True)
    op.drop_index('ix_deals_classification_status', table_name='deals', if_exists=True)
    op.drop_index('ix_deals_sector_classification', table_name='deals', if_exists=True)
    op.drop_index('ix_work_orders_wo_id', table_name='work_orders', if_exists=True)
    op.drop_index('ix_work_orders_snapshot_id', table_name='work_orders', if_exists=True)
    op.drop_index('ix_wo_customer_status', table_name='work_orders', if_exists=True)

    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_snapshot_id', db.models.snapshot.PortableUUID(length=36), nullable=True))
        batch_op.drop_constraint('fk_work_orders_snapshot_id_snapshot_metadata', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_work_orders_last_seen_snapshot_id_snapshot_metadata',
            'snapshot_metadata',
            ['last_seen_snapshot_id'],
            ['snapshot_id'],
            ondelete='SET NULL',
        )
        batch_op.drop_constraint('pk_work_orders', type_='primary')
        batch_op.create_primary_key('pk_work_orders', ['wo_id'])
        batch_op.create_index('ix_work_orders_last_seen_snapshot_id', ['last_seen_snapshot_id'], unique=False)
        batch_op.create_index('ix_wo_customer_status', ['customer_name', 'execution_status'], unique=False)
        batch_op.drop_column('snapshot_id')

    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_snapshot_id', db.models.snapshot.PortableUUID(length=36), nullable=True))
        batch_op.add_column(sa.Column('masked_deal_value', sa.Numeric(precision=18, scale=2), nullable=True))
        batch_op.drop_constraint('fk_deals_snapshot_id_snapshot_metadata', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_deals_last_seen_snapshot_id_snapshot_metadata',
            'snapshot_metadata',
            ['last_seen_snapshot_id'],
            ['snapshot_id'],
            ondelete='SET NULL',
        )
        batch_op.drop_constraint('pk_deals', type_='primary')
        batch_op.create_primary_key('pk_deals', ['item_id'])
        batch_op.create_index('ix_deals_last_seen_snapshot_id', ['last_seen_snapshot_id'], unique=False)
        batch_op.create_index('ix_deals_sector_classification', ['sector_service', 'classification'], unique=False)
        batch_op.create_index('ix_deals_classification_status', ['classification', 'value_status'], unique=False)
        batch_op.drop_column('normalized_deal_value')
        batch_op.drop_column('snapshot_id')
