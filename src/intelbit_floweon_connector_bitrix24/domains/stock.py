"""Домен «Складские остатки»: catalog.store.* (склады) + catalog.storeproduct.* (остатки).

Остаток на коробке задаётся по-разному в зависимости от складского учёта
(`catalog.document.mode.status`, стенд 4-17-28):

- учёт **включён** (`Y`) — `catalog.storeproduct.*` только читается (`add`/`update`
  на коробке нет: «Could not find description of add»), остаток меняется проведёнными
  документами: разница с текущим остатком → оприходование `S` (больше) или
  списание `D` (меньше); документу нужен ответственный (`responsibleId`, иначе
  «Required fields: responsibleId») — `documents_responsible_id` конфига коннектора;
- учёт **выключен** (`N`) — остаток товара в `catalog.product.update` (`quantity`).
"""

from __future__ import annotations

import logging
from typing import Any

from intelbit_bitrix24_client import Bitrix24Client, Bitrix24Error

from intelbit_floweon_connector_bitrix24 import fieldmaps

logger = logging.getLogger(__name__)


class StockDomain:
    """Склады и остатки товаров на складах."""

    def __init__(
        self,
        client: Bitrix24Client,
        *,
        document_currency: str = "RUB",
        documents_responsible_id: int | None = None,
    ) -> None:
        self._client = client
        self._document_currency = document_currency
        self._responsible_id = documents_responsible_id
        # Режим складского учёта не меняется на ходу — один запрос на процесс.
        self._inventory_mode: bool | None = None

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

    # --- установка остатка (upsert пресета) -------------------------------- #

    async def inventory_mode(self) -> bool:
        """Включён ли складской учёт (тогда остатки меняются только документами)."""
        if self._inventory_mode is None:
            env = await self._client.call("catalog.document.mode.status")
            self._inventory_mode = env.get("result") == "Y"
        return self._inventory_mode

    async def set_amount(
        self, store_id: int, product_id: int, amount: float, *, title: str
    ) -> dict[str, Any]:
        """Довести остаток товара на складе до `amount`.

        Returns:
            `{"op": "noop"|"document"|"quantity", …}`; для документа — тип, id, разница.
        """
        if not await self.inventory_mode():
            await self._client.call(
                "catalog.product.update", {"id": product_id, "fields": {"quantity": amount}}
            )
            return {"op": "quantity", "id": product_id}

        rows = await self.list_stock(store_id, product_id)
        current = float(rows[0].get("amount") or 0) if rows else 0.0
        delta = float(amount) - current
        if delta == 0:
            return {"op": "noop", "id": rows[0]["id"] if rows else None}

        if self._responsible_id is None:
            raise ValueError(
                "остаток при складском учёте меняется документом: задайте "
                "documents_responsible_id (ответственный документа) в конфиге коннектора"
            )
        doc_type, store_key = ("S", "storeTo") if delta > 0 else ("D", "storeFrom")
        env = await self._client.call(
            "catalog.document.add",
            {
                "fields": {
                    "docType": doc_type,
                    "currency": self._document_currency,
                    "responsibleId": self._responsible_id,
                    "title": title,
                }
            },
        )
        doc_id = int(env["result"]["document"]["id"])
        element: dict[str, Any] = {
            "docId": doc_id,
            "elementId": product_id,
            store_key: store_id,
            "amount": abs(delta),
        }
        if doc_type == "S":
            element["purchasingPrice"] = 0
        try:
            await self._client.call("catalog.document.element.add", {"fields": element})
            await self._client.call("catalog.document.conduct", {"id": doc_id})
        except BaseException:
            # Любой исход, включая отмену задачи. Если conduct прошёл, а ответ потерян,
            # удаление проведённого документа коробка отклонит — он останется (верно).
            # Непроведённый документ не оставляем: следующий прогон создаст новый.
            try:
                await self._client.call("catalog.document.deleteList", {"documentIds": [doc_id]})
            except Bitrix24Error:
                logger.warning("Bitrix24: не удалён непроведённый документ %s", doc_id)
            raise
        return {"op": "document", "doc_type": doc_type, "doc_id": doc_id, "delta": delta}
