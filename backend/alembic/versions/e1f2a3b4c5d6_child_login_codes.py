"""child login codes: permanent WORD-1234 per child, per-address attempt locks

Revision ID: e1f2a3b4c5d6
Revises: c4e6a8b0d2f4
Create Date: 2026-09-27 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "c4e6a8b0d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("children", sa.Column("code_word", sa.String(length=4), nullable=True))
    op.add_column("children", sa.Column("code_pin", sa.String(length=4), nullable=True))
    op.add_column(
        "children", sa.Column("code_rotated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(op.f("uq_children_code_word"), "children", ["code_word"])
    op.create_table(
        "login_locks",
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_word", sa.String(length=4), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("ip", name=op.f("pk_login_locks")),
    )


def downgrade() -> None:
    op.drop_table("login_locks")
    op.drop_constraint(op.f("uq_children_code_word"), "children", type_="unique")
    op.drop_column("children", "code_rotated_at")
    op.drop_column("children", "code_pin")
    op.drop_column("children", "code_word")
