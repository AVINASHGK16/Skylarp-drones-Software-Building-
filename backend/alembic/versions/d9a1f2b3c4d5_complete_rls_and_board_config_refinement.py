"""complete_rls_and_board_config_refinement

Revision ID: d9a1f2b3c4d5
Revises: c73081e64bf2
Create Date: 2026-11-10 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9a1f2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'c73081e64bf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Refine tenant_board_configs constraints to allow multiple boards of the same type
    with op.batch_alter_table('tenant_board_configs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tenant_board_type', type_='unique')
        batch_op.create_unique_constraint('uq_connection_board_id', ['connection_id', 'monday_board_id'])

    # 2. Complete RLS Coverage on verified_domains and tenant_memberships
    if is_postgres:
        # Enable and FORCE RLS on verified_domains
        op.execute(sa.text("ALTER TABLE verified_domains ENABLE ROW LEVEL SECURITY;"))
        op.execute(sa.text("ALTER TABLE verified_domains FORCE ROW LEVEL SECURITY;"))
        op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_verified_domains ON verified_domains;"))
        op.execute(
            sa.text(
                "CREATE POLICY tenant_isolation_verified_domains ON verified_domains "
                "FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
                "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);"
            )
        )

        # Enable and FORCE RLS on tenant_memberships
        op.execute(sa.text("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;"))
        op.execute(sa.text("ALTER TABLE tenant_memberships FORCE ROW LEVEL SECURITY;"))
        op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_tenant_memberships ON tenant_memberships;"))
        op.execute(
            sa.text(
                "CREATE POLICY tenant_isolation_tenant_memberships ON tenant_memberships "
                "FOR ALL "
                "USING ("
                "  tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
                "  OR ("
                "    NULLIF(current_setting('app.current_tenant_id', true), '') IS NULL "
                "    AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
                "  )"
                ") "
                "WITH CHECK ("
                "  tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
                ");"
            )
        )

        # Ensure skylarp_app_user exists with NOSUPERUSER NOBYPASSRLS
        op.execute(
            sa.text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'skylarp_app_user') THEN "
                "CREATE ROLE skylarp_app_user NOSUPERUSER NOBYPASSRLS; "
                "END IF; "
                "ALTER ROLE skylarp_app_user NOSUPERUSER NOBYPASSRLS; "
                "END $$;"
            )
        )
        op.execute(sa.text("GRANT USAGE, CREATE ON SCHEMA public TO skylarp_app_user;"))
        op.execute(sa.text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO skylarp_app_user;"))
        op.execute(sa.text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO skylarp_app_user;"))
        op.execute(sa.text("ALTER ROLE skylarp_app_user SET search_path TO public;"))


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_tenant_memberships ON tenant_memberships;"))
        op.execute(sa.text("ALTER TABLE tenant_memberships NO FORCE ROW LEVEL SECURITY;"))
        op.execute(sa.text("ALTER TABLE tenant_memberships DISABLE ROW LEVEL SECURITY;"))

        op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_verified_domains ON verified_domains;"))
        op.execute(sa.text("ALTER TABLE verified_domains NO FORCE ROW LEVEL SECURITY;"))
        op.execute(sa.text("ALTER TABLE verified_domains DISABLE ROW LEVEL SECURITY;"))

    with op.batch_alter_table('tenant_board_configs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_connection_board_id', type_='unique')
        batch_op.create_unique_constraint('uq_tenant_board_type', ['tenant_id', 'board_type'])

