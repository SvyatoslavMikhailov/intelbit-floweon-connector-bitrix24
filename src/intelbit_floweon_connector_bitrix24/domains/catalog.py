"""Домен «Материалы и цены»: catalog.product.* + catalog.price.* (новый API).

Методы `catalog.*` оборачивают результат в объект: список — под ключом
множественного числа (`products`/`prices`), одиночная запись — под ключом
единственного (`product`/`price`), запись add/update — под `element`.
"""

from __future__ import annotations

from typing import Any

from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24 import fieldmaps


def _element_id(env: dict[str, Any]) -> int:
    result = env.get("result", {})
    element = result.get("element", result) if isinstance(result, dict) else {}
    return int(element["id"])


class CatalogDomain:
    """Товары торгового каталога и их цены."""

    def __init__(self, client: Bitrix24Client, *, iblock_id: int | None = None,
                 price_type_id: int | None = None) -> None:
        self._client = client
        self._iblock_id = iblock_id
        self._price_type_id = price_type_id

    # --- товары ----------------------------------------------------------- #

    async def list_records(
        self,
        filter: dict[str, Any] | None = None,
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        b24_filter = fieldmaps.to_bitrix(filter or {}, fieldmaps.PRODUCT)
        if self._iblock_id is not None and "iblockId" not in b24_filter:
            b24_filter["iblockId"] = self._iblock_id
        params: dict[str, Any] = {"filter": b24_filter}
        if select:
            params["select"] = select
        rows = [
            row
            async for row in self._client.list_all(
                "catalog.product.list", params, result_key="products"
            )
        ]
        return [fieldmaps.to_canonical(r, fieldmaps.PRODUCT) for r in rows]

    async def get(self, product_id: int) -> dict[str, Any]:
        env = await self._client.call("catalog.product.get", {"id": product_id})
        result = env.get("result", {})
        raw = result.get("product", {}) if isinstance(result, dict) else {}
        return fieldmaps.to_canonical(raw, fieldmaps.PRODUCT)

    async def add(self, data: dict[str, Any]) -> int:
        fields = fieldmaps.to_bitrix(data, fieldmaps.PRODUCT)
        if self._iblock_id is not None and "iblockId" not in fields:
            fields["iblockId"] = self._iblock_id
        env = await self._client.call("catalog.product.add", {"fields": fields})
        return _element_id(env)

    async def update(self, product_id: int, data: dict[str, Any]) -> bool:
        fields = fieldmaps.to_bitrix(data, fieldmaps.PRODUCT)
        env = await self._client.call(
            "catalog.product.update", {"id": product_id, "fields": fields}
        )
        return bool(env.get("result"))

    # --- цены ------------------------------------------------------------- #

    async def list_prices(self, product_id: int | None = None) -> list[dict[str, Any]]:
        b24_filter: dict[str, Any] = {}
        if product_id is not None:
            b24_filter["productId"] = product_id
        if self._price_type_id is not None:
            b24_filter["catalogGroupId"] = self._price_type_id
        params = {"filter": b24_filter} if b24_filter else {}
        rows = [
            row
            async for row in self._client.list_all(
                "catalog.price.list", params, result_key="prices"
            )
        ]
        return [fieldmaps.to_canonical(r, fieldmaps.PRICE) for r in rows]

    async def add_price(self, data: dict[str, Any]) -> int:
        fields = fieldmaps.to_bitrix(data, fieldmaps.PRICE)
        if self._price_type_id is not None and "catalogGroupId" not in fields:
            fields["catalogGroupId"] = self._price_type_id
        env = await self._client.call("catalog.price.add", {"fields": fields})
        return _element_id(env)

    async def update_price(self, price_id: int, data: dict[str, Any]) -> bool:
        fields = fieldmaps.to_bitrix(data, fieldmaps.PRICE)
        env = await self._client.call("catalog.price.update", {"id": price_id, "fields": fields})
        return bool(env.get("result"))

    async def price_types(self) -> list[dict[str, Any]]:
        rows = [
            row
            async for row in self._client.list_all(
                "catalog.priceType.list", {}, result_key="priceTypes"
            )
        ]
        return rows
