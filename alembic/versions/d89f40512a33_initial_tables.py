"""initial_tables

Revision ID: d89f40512a33
Revises:
Create Date: 2026-02-10 23:01:18.678542

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d89f40512a33"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create users and meal_entries tables."""
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False, unique=True, index=True),
        sa.Column("goal", sa.String(32), nullable=True),
        sa.Column("tz_mode", sa.String(16), nullable=True),
        sa.Column("tz_name", sa.String(64), nullable=True),
        sa.Column("tz_offset_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "meal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("photo_file_id", sa.String(256), nullable=True),
        sa.Column("consumed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("tz_name_snapshot", sa.String(64), nullable=True),
        sa.Column("tz_offset_minutes_snapshot", sa.Integer(), nullable=True),
        sa.Column("meal_name", sa.String(256), nullable=False),
        sa.Column("calories_kcal", sa.Integer(), nullable=False),
        sa.Column("protein_g", sa.Float(), nullable=False),
        sa.Column("carbs_g", sa.Float(), nullable=False),
        sa.Column("fat_g", sa.Float(), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("volume_ml", sa.Integer(), nullable=True),
        sa.Column("caffeine_mg", sa.Integer(), nullable=True),
        sa.Column("likely_ingredients_json", postgresql.JSONB(), nullable=True),
        sa.Column("raw_ai_response", postgresql.JSONB(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("tg_chat_id", "tg_message_id", name="uq_meal_chat_message"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_meal_user"),
    )

    # Partial index for fast lookups on active meals by user + date.
    op.create_index(
        "ix_meal_user_localdate_active",
        "meal_entries",
        ["user_id", "local_date"],
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop meal_entries and users tables."""
    op.drop_index("ix_meal_user_localdate_active", table_name="meal_entries")
    op.drop_table("meal_entries")
    op.drop_table("users")
