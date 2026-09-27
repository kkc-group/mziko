from pydantic import BaseModel

from app.schemas.me import ChildOut


class PairIn(BaseModel):
    device_name: str | None = None


class PairOut(BaseModel):
    device_token: str
    child: ChildOut
