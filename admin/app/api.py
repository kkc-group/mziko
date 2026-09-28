"""The back office's only door to the data: an HTTP client for /api/admin/*.

It never touches the database. It authenticates with the shared ADMIN_API_TOKEN.
"""

from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def make_client(api_url: str, admin_api_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{api_url.rstrip('/')}/api/admin",
        headers={"Authorization": f"Bearer {admin_api_token}"},
        timeout=10,
    )


class AdminApi:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _get(self, path: str) -> Any:
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise ApiError(0, str(exc)) from exc
        if response.is_error:
            try:
                detail = str(response.json().get("detail", response.text))
            except ValueError:
                detail = response.text
            raise ApiError(response.status_code, detail)
        return response.json()

    async def parents(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = await self._get("/parents")
        return rows

    async def parent(self, parent_id: int) -> dict[str, Any]:
        """Raises ApiError(404, ...) when the id is unknown, as the API's own 404 says."""
        data: dict[str, Any] = await self._get(f"/parents/{parent_id}")
        return data
