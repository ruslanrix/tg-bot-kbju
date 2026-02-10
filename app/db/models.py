"""SQLAlchemy 2.0 declarative models: User and MealEntry.

Matches spec sections 7.1–7.3.  All timestamps are stored as UTC.
``MealEntry.local_date`` is computed once at save time and never
re-bucketed when the user changes timezone.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class User(Base):
    """Telegram user with goal and timezone preferences (spec §7.1)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)

    # Goal label: maintenance / deficit / bulk (or None if not set yet).
    goal: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Timezone: either IANA city name or fixed UTC offset.
    tz_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tz_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tz_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    meals: Mapped[list[MealEntry]] = relationship(back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User tg={self.tg_user_id} goal={self.goal}>"


class MealEntry(Base):
    """A single logged meal with nutrition data (spec §7.2).

    Soft-deleted meals (``is_deleted=True``) are kept in the database
    but excluded from all stats, history, and report queries.
    """

    __tablename__ = "meal_entries"
    __table_args__ = (
        UniqueConstraint("tg_chat_id", "tg_message_id", name="uq_meal_chat_message"),
        Index(
            "ix_meal_user_localdate_active",
            "user_id",
            "local_date",
            postgresql_where="is_deleted = false",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Telegram message identifiers (idempotency key).
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tg_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Source type: "text" or "photo".
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Time fields.
    consumed_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Timezone snapshot at save time (for observability; no re-bucketing).
    tz_name_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tz_offset_minutes_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Nutrition data.
    meal_name: Mapped[str] = mapped_column(String(256), nullable=False)
    calories_kcal: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caffeine_mg: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Structured data stored as JSON.
    likely_ingredients_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_ai_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Soft-delete support.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="meals", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MealEntry {self.meal_name} {self.calories_kcal}kcal>"
