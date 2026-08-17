"""Add durable private conversations and messages.

Revision ID: b31f7a9d2c84
Revises: 8d4f2a6c1b70
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "b31f7a9d2c84"
down_revision = "8d4f2a6c1b70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_low_id", sa.Integer(), nullable=False),
        sa.Column("user_high_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("user_low_id < user_high_id", name="ck_conversations_ordered_pair"),
        sa.ForeignKeyConstraint(["user_high_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_low_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_conversations_pair"),
    )
    op.create_index("ix_conversations_high_activity", "conversations", ["user_high_id", "last_activity_at"])
    op.create_index("ix_conversations_low_activity", "conversations", ["user_low_id", "last_activity_at"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at", "id"])
    op.create_index("ix_messages_conversation_unread", "messages", ["conversation_id", "read_at", "sender_id"])


def downgrade():
    op.drop_index("ix_messages_conversation_unread", table_name="messages")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_low_activity", table_name="conversations")
    op.drop_index("ix_conversations_high_activity", table_name="conversations")
    op.drop_table("conversations")
