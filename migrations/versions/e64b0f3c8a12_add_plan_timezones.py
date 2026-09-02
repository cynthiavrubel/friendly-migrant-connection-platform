"""Add IANA timezone context to Community Plans.

Revision ID: e64b0f3c8a12
Revises: d53a9e2b7f01
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "e64b0f3c8a12"
down_revision = "d53a9e2b7f01"
branch_labels = None
depends_on = None


def upgrade():
    # Sprint 9 interpreted wall-clock input as UTC. Backfilling UTC preserves
    # every existing plan's stored instant and previous display meaning.
    op.add_column("community_plans", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.execute(sa.text("UPDATE community_plans SET timezone = 'UTC' WHERE timezone IS NULL"))
    with op.batch_alter_table("community_plans") as batch_op:
        batch_op.alter_column("timezone", existing_type=sa.String(length=64), nullable=False)


def downgrade():
    with op.batch_alter_table("community_plans") as batch_op:
        batch_op.drop_column("timezone")
