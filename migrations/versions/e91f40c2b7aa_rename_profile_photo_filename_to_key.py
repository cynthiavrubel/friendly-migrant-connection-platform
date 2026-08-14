"""Rename profile photo filename to storage-neutral key.

Revision ID: e91f40c2b7aa
Revises: c7f214d58a39
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "e91f40c2b7aa"
down_revision = "c7f214d58a39"
branch_labels = None
depends_on = None

OLD_COLUMN = "profile_photo_filename"
NEW_COLUMN = "profile_photo_key"
FINAL_INDEX = "ux_profiles_profile_photo_key"


def _photo_indexes(inspector, column):
    """Return real index names instead of assuming Alembic's requested name."""
    return [
        index
        for index in inspector.get_indexes("profiles")
        if index.get("column_names") == [column]
    ]


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"]: column for column in inspector.get_columns("profiles")}

    if OLD_COLUMN in columns and NEW_COLUMN in columns:
        raise RuntimeError(
            "Both profile photo columns exist; refusing to guess which value to preserve. "
            "Inspect the profiles table before retrying."
        )
    if OLD_COLUMN not in columns and NEW_COLUMN not in columns:
        raise RuntimeError("Neither expected profile photo column exists in profiles.")

    # SQLite cannot rename/drop its implicit unique auto-index directly. Batch
    # recreation remains appropriate for isolated test databases.
    if connection.dialect.name == "sqlite" and OLD_COLUMN in columns:
        with op.batch_alter_table("profiles") as batch_op:
            batch_op.drop_constraint("uq_profiles_profile_photo_filename", type_="unique")
            batch_op.alter_column(
                OLD_COLUMN,
                new_column_name=NEW_COLUMN,
                existing_type=columns[OLD_COLUMN]["type"],
                type_=sa.String(length=255),
                existing_nullable=columns[OLD_COLUMN]["nullable"],
            )
        op.create_index(FINAL_INDEX, "profiles", [NEW_COLUMN], unique=True)
        return

    if OLD_COLUMN in columns:
        # MySQL created this unique index as `profile_photo_filename`, despite the
        # constraint name requested by c7f214d58a39. Discover its real name.
        for index in _photo_indexes(inspector, OLD_COLUMN):
            if index.get("unique"):
                op.drop_index(index["name"], table_name="profiles")

        op.alter_column(
            "profiles",
            OLD_COLUMN,
            new_column_name=NEW_COLUMN,
            existing_type=columns[OLD_COLUMN]["type"],
            type_=sa.String(length=255),
            existing_nullable=columns[OLD_COLUMN]["nullable"],
        )
    else:
        # Recovery path if MySQL completed the rename before a later DDL failed.
        column = columns[NEW_COLUMN]
        if getattr(column["type"], "length", None) != 255:
            op.alter_column(
                "profiles",
                NEW_COLUMN,
                existing_type=column["type"],
                type_=sa.String(length=255),
                existing_nullable=column["nullable"],
            )

    inspector = sa.inspect(connection)
    indexes = _photo_indexes(inspector, NEW_COLUMN)
    final_index = next((index for index in indexes if index["name"] == FINAL_INDEX), None)
    if final_index and final_index.get("unique"):
        return

    # Recover from a prior attempt that created a differently named or non-unique index.
    for index in indexes:
        op.drop_index(index["name"], table_name="profiles")
    op.create_index(FINAL_INDEX, "profiles", [NEW_COLUMN], unique=True)


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"]: column for column in inspector.get_columns("profiles")}
    if NEW_COLUMN not in columns:
        return

    for index in _photo_indexes(inspector, NEW_COLUMN):
        op.drop_index(index["name"], table_name="profiles")
    op.alter_column(
        "profiles",
        NEW_COLUMN,
        new_column_name=OLD_COLUMN,
        existing_type=columns[NEW_COLUMN]["type"],
        type_=sa.String(length=80),
        existing_nullable=columns[NEW_COLUMN]["nullable"],
    )
    op.create_index(OLD_COLUMN, "profiles", [OLD_COLUMN], unique=True)
