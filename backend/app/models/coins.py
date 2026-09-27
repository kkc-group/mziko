"""Weekly coin jars and the ledger every coin passes through."""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.people import Child


class WeekStatus(enum.StrEnum):
    open = "open"
    paid = "paid"


class CoinReason(enum.StrEnum):
    answer = "answer"
    word_learned = "word_learned"


class Week(Base):
    """Monday-to-Sunday week (Asia/Tbilisi) for one child.

    `coins` is always the sum of `coin_ledger.amount` for this week and is
    updated in the same transaction as the ledger row.
    """

    __tablename__ = "weeks"
    __table_args__ = (UniqueConstraint("child_id", "week_start"),)

    id: Mapped[IntPK]
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[WeekStatus] = mapped_column(
        Enum(WeekStatus, name="week_status", native_enum=True),
        nullable=False,
        default=WeekStatus.open,
        server_default="open",
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lari_paid: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    rate_snapshot: Mapped[int | None] = mapped_column(Integer)
    cap_snapshot: Mapped[int | None] = mapped_column(Integer)

    child: Mapped[Child] = relationship()
    ledger: Mapped[list["CoinLedger"]] = relationship(back_populates="week")


class CoinLedger(Base):
    __tablename__ = "coin_ledger"

    id: Mapped[IntPK]
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_id: Mapped[int] = mapped_column(
        ForeignKey("weeks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answer_id: Mapped[int | None] = mapped_column(ForeignKey("answers.id", ondelete="SET NULL"))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[CoinReason] = mapped_column(
        Enum(CoinReason, name="coin_reason", native_enum=True), nullable=False
    )
    created_at: Mapped[CreatedAt]

    week: Mapped[Week] = relationship(back_populates="ledger")
