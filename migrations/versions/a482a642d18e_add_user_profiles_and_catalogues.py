"""Add user profiles and profile catalogues.

Revision ID: a482a642d18e
Revises: 5155e70ff17c
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "a482a642d18e"
down_revision = "5155e70ff17c"
branch_labels = None
depends_on = None


def upgrade():
    # This remains nullable so the migration is safe when development users exist.
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))

    op.create_table(
        "connection_intents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "interests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_interests_category"), "interests", ["category"], unique=False)
    op.create_table(
        "languages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("gender", sa.String(length=24), nullable=False),
        sa.Column("gender_description", sa.String(length=50), nullable=True),
        sa.Column("bio", sa.String(length=500), nullable=True),
        sa.Column("home_country_code", sa.String(length=2), nullable=False),
        sa.Column("home_city", sa.String(length=100), nullable=False),
        sa.Column("discovery_country_code", sa.String(length=2), nullable=False),
        sa.Column("discovery_city", sa.String(length=100), nullable=False),
        sa.Column("open_to_connections", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "profile_connection_intents",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("connection_intent_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["connection_intent_id"], ["connection_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id", "connection_intent_id"),
    )
    op.create_table(
        "profile_interests",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("interest_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["interest_id"], ["interests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id", "interest_id"),
    )
    op.create_table(
        "profile_languages",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("language_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["language_id"], ["languages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id", "language_id"),
    )


def downgrade():
    op.drop_table("profile_languages")
    op.drop_table("profile_interests")
    op.drop_table("profile_connection_intents")
    op.drop_table("profiles")
    op.drop_table("languages")
    op.drop_index(op.f("ix_interests_category"), table_name="interests")
    op.drop_table("interests")
    op.drop_table("connection_intents")
    op.drop_column("users", "date_of_birth")
