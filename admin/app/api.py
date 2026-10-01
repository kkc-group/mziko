"""The back office's only door to the data: HTTP clients for the API.

Neither client touches the database. `AdminApi` reads /api/admin/* with the
shared ADMIN_API_TOKEN for the owner; `ParentApi` reads /api/parent/* for the
parents' cabinet with the shared BOT_API_TOKEN, naming the parent in
`X-Telegram-Id` exactly as the Telegram bot does, so the API applies the same
boundary: a parent sees their own children and nothing else.
"""

from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def _body(response: httpx.Response) -> Any:
    if response.is_error:
        try:
            detail = str(response.json().get("detail", response.text))
        except ValueError:
            detail = response.text
        raise ApiError(response.status_code, detail)
    return response.json()


async def _get(client: httpx.AsyncClient, path: str, headers: dict[str, str]) -> Any:
    try:
        response = await client.get(path, headers=headers)
    except httpx.HTTPError as exc:
        raise ApiError(0, str(exc)) from exc
    return _body(response)


def make_client(api_url: str, admin_api_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{api_url.rstrip('/')}/api/admin",
        headers={"Authorization": f"Bearer {admin_api_token}"},
        timeout=10,
    )


class AdminApi:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def parents(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = await _get(self._client, "/parents", {})
        return rows

    async def parent(self, parent_id: int) -> dict[str, Any]:
        """Raises ApiError(404, ...) when the id is unknown, as the API's own 404 says."""
        data: dict[str, Any] = await _get(self._client, f"/parents/{parent_id}", {})
        return data


def make_parent_client(api_url: str, bot_api_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{api_url.rstrip('/')}/api/parent",
        headers={"Authorization": f"Bearer {bot_api_token}"},
        timeout=10,
    )


class ParentApi:
    """Calls on behalf of one parent each; 403 means the API knows no such parent."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def children(self, telegram_id: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = await _get(
            self._client, "/children", {"X-Telegram-Id": str(telegram_id)}
        )
        return rows

    async def set_photo(self, telegram_id: int, photo_url: str) -> None:
        """The cabinet's only write: the profile photo Telegram showed on entry."""
        try:
            response = await self._client.put(
                "/me/photo",
                json={"photo_url": photo_url},
                headers={"X-Telegram-Id": str(telegram_id)},
            )
        except httpx.HTTPError as exc:
            raise ApiError(0, str(exc)) from exc
        if response.is_error:
            raise ApiError(response.status_code, response.text)

    async def progress(self, telegram_id: int, child_id: int) -> dict[str, Any]:
        data: dict[str, Any] = await _get(
            self._client, f"/children/{child_id}/progress", {"X-Telegram-Id": str(telegram_id)}
        )
        return data
