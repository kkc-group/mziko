from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.me import ChildOut


class LoginIn(BaseModel):
    word: str = Field(min_length=4, max_length=4)
    pin: str = Field(pattern=r"^\d{4}$")
    device_name: str | None = None


class LoginOut(BaseModel):
    device_token: str
    child: ChildOut


class WrongCodeDetail(BaseModel):
    error: Literal["wrong_code"] = "wrong_code"
    attempts_left: int


class LockedDetail(BaseModel):
    error: Literal["locked"] = "locked"
    locked_until: datetime


class LockStatusOut(BaseModel):
    locked_until: datetime | None
    word: str | None
    pin_rotated: bool
