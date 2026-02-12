"""Add user language and activity timestamps.

Revision ID: a1b2c3d4e5f6
Revises: d89f40512a33
Create Date: 2026-02-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "d89f40512a33"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.String(2), nullable=False, server_default="EN"))
    op.add_column("users", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_reminder_at")
    op.drop_column("users", "last_activity_at")
    op.drop_column("users", "language")
