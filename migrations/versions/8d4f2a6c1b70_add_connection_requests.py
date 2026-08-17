"""Add mutual connection request state.

Revision ID: 8d4f2a6c1b70
Revises: e91f40c2b7aa
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "8d4f2a6c1b70"
down_revision = "e91f40c2b7aa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connection_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("pair_low_id", sa.Integer(), nullable=False),
        sa.Column("pair_high_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("introductory_message", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("sender_id <> recipient_id", name="ck_connection_requests_distinct_users"),
        sa.CheckConstraint("pair_low_id < pair_high_id", name="ck_connection_requests_ordered_pair"),
        sa.CheckConstraint(
            "(sender_id = pair_low_id AND recipient_id = pair_high_id) OR "
            "(sender_id = pair_high_id AND recipient_id = pair_low_id)",
            name="ck_connection_requests_pair_members",
        ),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="ck_connection_requests_status"),
        sa.ForeignKeyConstraint(["pair_high_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pair_low_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pair_low_id", "pair_high_id", name="uq_connection_requests_pair"),
    )
    op.create_index("ix_connection_requests_recipient_status", "connection_requests", ["recipient_id", "status"])
    op.create_index("ix_connection_requests_sender_status", "connection_requests", ["sender_id", "status"])


def downgrade():
    op.drop_index("ix_connection_requests_sender_status", table_name="connection_requests")
    op.drop_index("ix_connection_requests_recipient_status", table_name="connection_requests")
    op.drop_table("connection_requests")
