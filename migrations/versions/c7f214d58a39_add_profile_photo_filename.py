"""Add profile photo filename.

Revision ID: c7f214d58a39
Revises: a482a642d18e
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "c7f214d58a39"
down_revision = "a482a642d18e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.add_column(sa.Column("profile_photo_filename", sa.String(length=80), nullable=True))
        batch_op.create_unique_constraint("uq_profiles_profile_photo_filename", ["profile_photo_filename"])


def downgrade():
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.drop_constraint("uq_profiles_profile_photo_filename", type_="unique")
        batch_op.drop_column("profile_photo_filename")
