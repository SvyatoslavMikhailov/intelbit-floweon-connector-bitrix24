"""Домен «Сделки»: crm.deal.* + товарные строки crm.deal.productrows.*."""

from __future__ import annotations

from typing import Any

from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24 import fieldmaps


class DealsDomain:
    """Сделки Bitrix24 со стандартными полями и товарными строками."""

    def __init__(self, client: Bitrix24Client) -> None:
        self._client = client

    async def list_records(
        self,
        filter: dict[str, Any] | None = None,
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = fieldmaps.to_bitrix(filter, fieldmaps.DEAL)
        params["select"] = select or list(fieldmaps.DEAL.values())
        rows = [row async for row in self._client.list_all("crm.deal.list", params)]
        return [fieldmaps.to_canonical(r, fieldmaps.DEAL) for r in rows]

    async def get(self, deal_id: int | str) -> dict[str, Any]:
        env = await self._client.call("crm.deal.get", {"id": deal_id})
        return fieldmaps.to_canonical(env.get("result", {}) or {}, fieldmaps.DEAL)

    async def add(self, data: dict[str, Any]) -> int:
        fields = fieldmaps.to_bitrix(data, fieldmaps.DEAL)
        env = await self._client.call("crm.deal.add", {"fields": fields})
        return int(env["result"])

    async def update(self, deal_id: int | str, data: dict[str, Any]) -> bool:
        fields = fieldmaps.to_bitrix(data, fieldmaps.DEAL)
        env = await self._client.call("crm.deal.update", {"id": deal_id, "fields": fields})
        return bool(env.get("result"))

    async def delete(self, deal_id: int | str) -> bool:
        env = await self._client.call("crm.deal.delete", {"id": deal_id})
        return bool(env.get("result"))

    # --- товарные строки -------------------------------------------------- #

    async def get_productrows(self, deal_id: int | str) -> list[dict[str, Any]]:
        env = await self._client.call("crm.deal.productrows.get", {"id": deal_id})
        rows = env.get("result", []) or []
        return [fieldmaps.to_canonical(r, fieldmaps.DEAL_PRODUCTROW) for r in rows]

    async def set_productrows(self, deal_id: int | str, rows: list[dict[str, Any]]) -> bool:
        b24_rows = [fieldmaps.to_bitrix(r, fieldmaps.DEAL_PRODUCTROW) for r in rows]
        env = await self._client.call("crm.deal.productrows.set", {"id": deal_id, "rows": b24_rows})
        return bool(env.get("result"))
