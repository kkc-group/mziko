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
    # Permanent login code "WORD-1234": the word is unique and never changes,
    # the parent can re-issue the pin (see services.login_codes).
    code_word: Mapped[str | None] = mapped_column(String(4), unique=True)
    code_pin: Mapped[str | None] = mapped_column(String(4))
    code_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]

    parents: Mapped[list[Parent]] = relationship(
        secondary=parent_children, back_populates="children"
    )
    devices: Mapped[list["Device"]] = relationship(back_populates="child")


class Device(Base):
    """A logged-in browser (iPad). Only the SHA-256 of the bearer token is stored."""

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


class LoginLock(Base):
    """Failed login attempts from one network address; three in a row lock it for an hour."""

    __tablename__ = "login_locks"

    ip: Mapped[str] = mapped_column(String(45), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # The word typed on the last failed attempt: re-issuing that child's pin lifts the lock.
    last_word: Mapped[str | None] = mapped_column(String(4))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
