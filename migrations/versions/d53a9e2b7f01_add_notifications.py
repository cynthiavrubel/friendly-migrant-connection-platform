"""Add derived in-app notifications.

Revision ID: d53a9e2b7f01
Revises: c42e8d1f6a90
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "d53a9e2b7f01"
down_revision = "c42e8d1f6a90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("related_entity_type", sa.String(length=32), nullable=True),
        sa.Column("related_entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type IN ('connection_request_received', 'connection_request_accepted', 'new_message', "
            "'plan_participant_joined', 'plan_participant_left', 'plan_participant_removed', 'plan_cancelled')",
            name="ck_notifications_type",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read_at"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notifications_coalesce",
        "notifications",
        ["user_id", "type", "related_entity_type", "related_entity_id", "read_at"],
    )


def downgrade():
    op.drop_index("ix_notifications_coalesce", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
