"""Add community plans and normalized participation.

Revision ID: c42e8d1f6a90
Revises: b31f7a9d2c84
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "c42e8d1f6a90"
down_revision = "b31f7a9d2c84"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "community_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=1200), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("city_normalized", sa.String(length=100), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meeting_place_text", sa.String(length=200), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("capacity >= 2 AND capacity <= 20", name="ck_community_plans_capacity"),
        sa.CheckConstraint("status IN ('active', 'cancelled')", name="ck_community_plans_status"),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plans_creator_start", "community_plans", ["creator_id", "starts_at"])
    op.create_index("ix_plans_location_status_start", "community_plans", ["country_code", "city_normalized", "status", "starts_at"])
    op.create_table(
        "plan_participants",
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["community_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id", "user_id"),
    )
    op.create_index("ix_plan_participants_user_joined", "plan_participants", ["user_id", "joined_at"])


def downgrade():
    op.drop_index("ix_plan_participants_user_joined", table_name="plan_participants")
    op.drop_table("plan_participants")
    op.drop_index("ix_plans_location_status_start", table_name="community_plans")
    op.drop_index("ix_plans_creator_start", table_name="community_plans")
    op.drop_table("community_plans")
