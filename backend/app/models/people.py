"""Parents, children and the devices children play on."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK

parent_children = Table(
    "parent_children",
    Base.metadata,
    Column("parent_id", ForeignKey("parents.id", ondelete="CASCADE"), primary_key=True),
    Column("child_id", ForeignKey("children.id", ondelete="CASCADE"), primary_key=True),
)


class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[IntPK]
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[CreatedAt]

    children: Mapped[list["Child"]] = relationship(
        secondary=parent_children, back_populates="parents"
    )


class Child(Base):
    __tablename__ = "children"

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Coins per 1 GEL.
    rate: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    # Weekly payout cap in GEL.
    cap_lari: Mapped[int] = mapped_column(Integer, nullable=False, default=15, server_default="15")
    show_hint: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[CreatedAt]

    parents: Mapped[list[Parent]] = relationship(
        secondary=parent_children, back_populates="children"
    )
    devices: Mapped[list["Device"]] = relationship(back_populates="child")


class Device(Base):
    """A paired browser (iPad). Only the SHA-256 of the bearer token is stored."""

    __tablename__ = "devices"

    id: Mapped[IntPK]
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[CreatedAt]
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    child: Mapped[Child] = relationship(back_populates="devices")


class PairCode(Base):
    """One-time pairing link issued by a parent in the bot; lives 15 minutes."""

    __tablename__ = "pair_codes"

    id: Mapped[IntPK]
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("parents.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]
