"""Add user blocks and private reports.

Revision ID: f75c1a4d9b20
Revises: e64b0f3c8a12
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "f75c1a4d9b20"
down_revision = "e64b0f3c8a12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_user_blocks_distinct_users"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_direction"),
    )
    op.create_index("ix_user_blocks_blocked_blocker", "user_blocks", ["blocked_id", "blocker_id"])
    op.create_table(
        "user_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=True),
        sa.Column("reported_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("details", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("reason IN ('harassment', 'hate_or_abuse', 'sexual_or_inappropriate', 'spam_or_scam', 'impersonation', 'unsafe_behavior', 'other')", name="ck_user_reports_reason"),
        sa.CheckConstraint("status IN ('open')", name="ck_user_reports_status"),
        sa.ForeignKeyConstraint(["reported_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_reports_reported_created", "user_reports", ["reported_user_id", "created_at"])
    op.create_index("ix_user_reports_reporter_created", "user_reports", ["reporter_id", "created_at"])


def downgrade():
    op.drop_index("ix_user_reports_reporter_created", table_name="user_reports")
    op.drop_index("ix_user_reports_reported_created", table_name="user_reports")
    op.drop_table("user_reports")
    op.drop_index("ix_user_blocks_blocked_blocker", table_name="user_blocks")
    op.drop_table("user_blocks")
