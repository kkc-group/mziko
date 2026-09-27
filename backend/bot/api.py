"""The bot's only door to the data: an HTTP client for /api/parent/*.

The bot never touches the database. It authenticates with the shared
BOT_API_TOKEN and names the parent it acts for in the X-Telegram-Id header;
the API decides what that parent may see.
"""

from datetime import date
from typing import Any

import httpx
from pydantic import TypeAdapter

from app.schemas.parent import (
    ChildCodeOut,
    ChildInfo,
    DeviceOut,
    DueReportOut,
    PayOut,
    ProgressOut,
    WeekReportOut,
)

CHILDREN = TypeAdapter(list[ChildInfo])
DEVICES = TypeAdapter(list[DeviceOut])
DUE = TypeAdapter(list[DueReportOut])


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def make_client(api_url: str, bot_api_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{api_url.rstrip('/')}/api/parent",
        headers={"Authorization": f"Bearer {bot_api_token}"},
        timeout=10,
    )


class ParentApi:
    """Calls on behalf of one parent (`telegram_id`), or the bot itself when unbound."""

    def __init__(self, client: httpx.AsyncClient, telegram_id: int | None = None) -> None:
        self._client = client
        self.telegram_id = telegram_id

    def for_parent(self, telegram_id: int) -> "ParentApi":
        return ParentApi(self._client, telegram_id)

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"X-Telegram-Id": str(self.telegram_id)} if self.telegram_id is not None else {}
        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.is_error:
            try:
                detail = str(response.json().get("detail", response.text))
            except ValueError:
                detail = response.text
            raise ApiError(response.status_code, detail)
        return response.json()

    # --- children -------------------------------------------------------------

    async def children(self) -> list[ChildInfo]:
        return CHILDREN.validate_python(await self._call("GET", "/children"))

    async def add_child(self, name: str) -> ChildInfo:
        return ChildInfo.model_validate(await self._call("POST", "/children", json={"name": name}))

    async def child(self, child_id: int) -> ChildInfo | None:
        return next((c for c in await self.children() if c.id == child_id), None)

    async def progress(self, child_id: int) -> ProgressOut:
        return ProgressOut.model_validate(await self._call("GET", f"/children/{child_id}/progress"))

    async def update_settings(
        self,
        child_id: int,
        *,
        rate: int | None = None,
        cap_lari: int | None = None,
        show_hint: bool | None = None,
    ) -> ChildInfo:
        body = {
            k: v
            for k, v in {"rate": rate, "cap_lari": cap_lari, "show_hint": show_hint}.items()
            if v is not None
        }
        return ChildInfo.model_validate(
            await self._call("PATCH", f"/children/{child_id}/settings", json=body)
        )

    # --- login code and devices ----------------------------------------------

    async def child_code(self, child_id: int) -> ChildCodeOut:
        return ChildCodeOut.model_validate(await self._call("GET", f"/children/{child_id}/code"))

    async def rotate_code(self, child_id: int) -> ChildCodeOut:
        return ChildCodeOut.model_validate(
            await self._call("POST", f"/children/{child_id}/code/rotate")
        )

    async def devices(self, child_id: int) -> list[DeviceOut]:
        return DEVICES.validate_python(await self._call("GET", f"/children/{child_id}/devices"))

    async def revoke_device(self, child_id: int, device_id: int) -> list[DeviceOut]:
        return DEVICES.validate_python(
            await self._call("DELETE", f"/children/{child_id}/devices/{device_id}")
        )

    # --- weeks ----------------------------------------------------------------

    async def report(self, child_id: int, week_start: date | None = None) -> WeekReportOut:
        params = {"week_start": week_start.isoformat()} if week_start else {}
        return WeekReportOut.model_validate(
            await self._call("GET", f"/children/{child_id}/report", params=params)
        )

    async def week(self, week_id: int) -> WeekReportOut:
        return WeekReportOut.model_validate(await self._call("GET", f"/weeks/{week_id}"))

    async def pay(self, week_id: int) -> PayOut:
        return PayOut.model_validate(await self._call("POST", f"/weeks/{week_id}/pay"))

    async def reports_due(self) -> list[DueReportOut]:
        return DUE.validate_python(await self._call("GET", "/reports/due"))
