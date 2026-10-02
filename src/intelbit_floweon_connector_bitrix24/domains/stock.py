"""Домен «Складские остатки»: catalog.store.* (склады) + catalog.storeproduct.* (остатки)."""

from __future__ import annotations

from typing import Any

from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24 import fieldmaps


class StockDomain:
    """Склады и остатки товаров на складах."""

    def __init__(self, client: Bitrix24Client) -> None:
        self._client = client

    # --- склады ----------------------------------------------------------- #

    async def list_stores(self, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = fieldmaps.to_bitrix(filter, fieldmaps.STORE)
        rows = [
            row
            async for row in self._client.list_all(
                "catalog.store.list", params, result_key="stores"
            )
        ]
        return [fieldmaps.to_canonical(r, fieldmaps.STORE) for r in rows]

    async def get_store(self, store_id: int) -> dict[str, Any]:
        env = await self._client.call("catalog.store.get", {"id": store_id})
        result = env.get("result", {})
        raw = result.get("store", {}) if isinstance(result, dict) else {}
        return fieldmaps.to_canonical(raw, fieldmaps.STORE)

    # --- остатки ---------------------------------------------------------- #

    async def list_stock(
        self,
        store_id: int | None = None,
        product_id: int | None = None,
    ) -> list[dict[str, Any]]:
        b24_filter: dict[str, Any] = {}
        if store_id is not None:
            b24_filter["storeId"] = store_id
        if product_id is not None:
            b24_filter["productId"] = product_id
        params = {"filter": b24_filter} if b24_filter else {}
        rows = [
            row
            async for row in self._client.list_all(
                "catalog.storeproduct.list", params, result_key="storeProducts"
            )
        ]
        return [fieldmaps.to_canonical(r, fieldmaps.STORE_PRODUCT) for r in rows]

    async def get_stock(self, store_product_id: int) -> dict[str, Any]:
        env = await self._client.call("catalog.storeproduct.get", {"id": store_product_id})
        result = env.get("result", {})
        raw = result.get("storeProduct", {}) if isinstance(result, dict) else {}
        return fieldmaps.to_canonical(raw, fieldmaps.STORE_PRODUCT)

    async def add_stock(self, data: dict[str, Any]) -> int:
        fields = fieldmaps.to_bitrix(data, fieldmaps.STORE_PRODUCT)
        env = await self._client.call("catalog.storeproduct.add", {"fields": fields})
        result = env.get("result", {})
        element = result.get("element", result) if isinstance(result, dict) else {}
        return int(element["id"])

    async def update_stock(self, store_product_id: int, data: dict[str, Any]) -> bool:
        fields = fieldmaps.to_bitrix(data, fieldmaps.STORE_PRODUCT)
        env = await self._client.call(
            "catalog.storeproduct.update", {"id": store_product_id, "fields": fields}
        )
        return bool(env.get("result"))
