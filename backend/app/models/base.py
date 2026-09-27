from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Explicit naming convention so Alembic migrations get stable constraint names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


IntPK = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]
CreatedAt = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False),
]
