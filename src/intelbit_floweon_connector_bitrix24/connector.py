"""Bitrix24Connector — коннектор Bitrix24 (коробка) для Интелбит.Фловеон (ADR-006).

Композиция четырёх доменных адаптеров поверх общего Bitrix24Client. Реализует
контракт `ConnectorPlugin` из floweon-sdk: lifecycle (init/start/stop/health_check/
reload) + read/write. Дополнительно — subscribe (приём исходящих вебхуков коробки).

Все методы idempotent относительно retry; in-memory state между вызовами не держим
(клиент открывает/закрывает соединение на каждый запрос).
"""

from __future__ import annotations

from typing import Any

import httpx
from floweon_sdk import ConnectorPlugin, PluginManifest, PluginType
from floweon_sdk.connector import PluginContext, PluginHealth
from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24.domains.catalog import CatalogDomain
from intelbit_floweon_connector_bitrix24.domains.companies import CompaniesDomain
from intelbit_floweon_connector_bitrix24.domains.deals import DealsDomain
from intelbit_floweon_connector_bitrix24.domains.stock import StockDomain
from intelbit_floweon_connector_bitrix24.webhooks import Bitrix24WebhookReceiver

_UPSERT_ENTITIES = frozenset({"product", "price", "store_product"})

_MANIFEST = PluginManifest(
    id="intelbit.floweon.connector.bitrix24",
    version="0.2.1",
    plugin_type=PluginType.CONNECTOR,
    name="Bitrix24 Connector",
    description="Коннектор Bitrix24 (CRM + Торговый каталог) для Интелбит.Фловеон",
    author="ООО Интелбит",
    license="Apache-2.0",
)


class Bitrix24Connector(ConnectorPlugin):
    """Коннектор Bitrix24-коробки: контрагенты, материалы+цены, остатки, сделки."""

    manifest = _MANIFEST

    def __init__(
        self,
        config: dict[str, Any],
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = _transport
        self._build()

    def _build(self) -> None:
        cfg = self.config
        self._client = Bitrix24Client(
            str(cfg["webhook_base_url"]),
            rps=float(cfg.get("rate_limit_rps", 2.0)),
            timeout=float(cfg.get("timeout", 30.0)),
            _transport=self._transport,
        )
        self.companies = CompaniesDomain(self._client)
        self.catalog = CatalogDomain(
            self._client,
            iblock_id=cfg.get("iblock_id"),
            price_type_id=cfg.get("price_type_id"),
        )
        self.stock = StockDomain(self._client)
        self.deals = DealsDomain(self._client)
        self.webhooks = Bitrix24WebhookReceiver(cfg.get("event_secret"))

    # --- lifecycle (ADR-006) --------------------------------------------- #

    async def init(self, context: PluginContext) -> None:
        self.config = context.config
        self._build()

    async def start(self) -> None:
        """Ресурсы создаются лениво на каждый вызов клиента — стартовать нечего."""

    async def stop(self) -> None:
        """Соединения не держим между вызовами — освобождать нечего."""

    async def health_check(self) -> PluginHealth:
        configured = bool(self.config.get("webhook_base_url"))
        return PluginHealth(
            healthy=configured,
            message="" if configured else "webhook_base_url не задан",
        )

    # --- read / write (ConnectorPlugin) ---------------------------------- #

    async def read(self, entity: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Прочитать записи сущности. `params.id` → одиночный get, иначе list."""
        params = params or {}
        entity_id = params.get("id")
        filter_ = params.get("filter")
        select = params.get("select")

        if entity == "company":
            if entity_id is not None:
                return [await self.companies.get(entity_id)]
            return await self.companies.list_records(filter_, select)
        if entity == "requisite":
            return await self.companies.list_requisites(params["company_id"])
        if entity == "product":
            if entity_id is not None:
                return [await self.catalog.get(entity_id)]
            return await self.catalog.list_records(filter_, select)
        if entity == "price":
            return await self.catalog.list_prices(params.get("product_id"))
        if entity == "store":
            if entity_id is not None:
                return [await self.stock.get_store(entity_id)]
            return await self.stock.list_stores(filter_)
        if entity == "store_product":
            return await self.stock.list_stock(params.get("store_id"), params.get("product_id"))
        if entity == "deal":
            if entity_id is not None:
                return [await self.deals.get(entity_id)]
            return await self.deals.list_records(filter_, select)
        if entity == "deal_productrows":
            return await self.deals.get_productrows(params["deal_id"])
        raise ValueError(f"Неизвестная сущность для read: {entity!r}")

    async def write(self, entity: str, data: dict[str, Any]) -> dict[str, Any]:
        """Записать сущность.

        Два контракта:
        - `data.op` ∈ {add, update, delete}, поля — в `data.fields` (прежний);
        - канонический запись маппинга пресета (без ключа `fields`) для `product`,
          `price`, `store_product` — upsert по `code` товара.
        """
        if "fields" not in data and entity in _UPSERT_ENTITIES:
            return await self._upsert(entity, data)
        op = data.get("op", "add")
        fields = data.get("fields", {})
        entity_id: Any = data.get("id")

        if entity == "company":
            return await self._crud(self.companies, op, entity_id, fields)
        if entity == "requisite":
            if op == "add":
                return {"id": await self.companies.add_requisite(fields)}
            if op == "update":
                return {"updated": await self.companies.update_requisite(entity_id, fields)}
            raise ValueError(f"requisite не поддерживает op={op!r}")
        if entity == "product":
            return await self._catalog_write(op, entity_id, fields)
        if entity == "price":
            if op == "add":
                return {"id": await self.catalog.add_price(fields)}
            if op == "update":
                return {"updated": await self.catalog.update_price(entity_id, fields)}
            raise ValueError(f"price не поддерживает op={op!r}")
        if entity == "store_product":
            if op == "add":
                return {"id": await self.stock.add_stock(fields)}
            if op == "update":
                return {"updated": await self.stock.update_stock(entity_id, fields)}
            raise ValueError(f"store_product не поддерживает op={op!r}")
        if entity == "deal":
            return await self._crud(self.deals, op, entity_id, fields)
        if entity == "deal_productrows":
            return {"updated": await self.deals.set_productrows(data["deal_id"], data["rows"])}
        raise ValueError(f"Неизвестная сущность для write: {entity!r}")

    async def subscribe(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        """Приём исходящего вебхука коробки → канонический Event с idempotency-key."""
        return self.webhooks.parse_event(body)

    # --- upsert по code (пресет b24-sap, 4-17-25) ------------------------- #

    async def _upsert(self, entity: str, data: dict[str, Any]) -> dict[str, Any]:
        # Служебные ключи ядра (_mode, _idempotency_key) и пустые значения не пишем.
        record = {k: v for k, v in data.items() if not k.startswith("_") and v is not None}
        code = record.get("code")
        if code in (None, ""):
            raise ValueError(f"upsert {entity}: поле code обязательно")
        code = str(code)
        if entity == "product":
            existing = await self.catalog.list_records({"code": code})
            if existing:
                product_id = int(existing[0]["id"])
                await self.catalog.update(product_id, record)
                return {"id": product_id, "op": "update", "code": code}
            return {"id": await self.catalog.add(record), "op": "add", "code": code}

        product_id = await self._product_id_by_code(code)
        if entity == "price":
            fields = {"product_id": product_id}
            fields.update({k: record[k] for k in ("price", "currency") if k in record})
            prices = await self.catalog.list_prices(product_id)
            if prices:
                price_id = int(prices[0]["id"])
                await self.catalog.update_price(price_id, fields)
                return {"id": price_id, "op": "update", "code": code}
            return {"id": await self.catalog.add_price(fields), "op": "add", "code": code}

        # store_product
        store_id = self.config.get("store_id")
        if store_id is None or store_id == "":
            raise ValueError(
                "upsert store_product: в конфиге коннектора не задан store_id (склад остатков)"
            )
        store = int(store_id)
        rows = await self.stock.list_stock(store, product_id)
        amount = record.get("amount")
        if rows:
            row_id = int(rows[0]["id"])
            await self.stock.update_stock(row_id, {"amount": amount})
            return {"id": row_id, "op": "update", "code": code}
        new_id = await self.stock.add_stock(
            {"store_id": store, "product_id": product_id, "amount": amount}
        )
        return {"id": new_id, "op": "add", "code": code}

    async def _product_id_by_code(self, code: str) -> int:
        products = await self.catalog.list_records({"code": code})
        if not products:
            raise ValueError(f"товар с code {code!r} не найден в каталоге Bitrix24")
        return int(products[0]["id"])

    # --- helpers ---------------------------------------------------------- #

    async def _crud(
        self,
        domain: CompaniesDomain | DealsDomain,
        op: str,
        entity_id: Any,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        if op == "add":
            return {"id": await domain.add(fields)}
        if op == "update":
            return {"updated": await domain.update(entity_id, fields)}
        if op == "delete":
            return {"deleted": await domain.delete(entity_id)}
        raise ValueError(f"Неизвестная операция write: {op!r}")

    async def _catalog_write(
        self, op: str, entity_id: Any, fields: dict[str, Any]
    ) -> dict[str, Any]:
        if op == "add":
            return {"id": await self.catalog.add(fields)}
        if op == "update":
            return {"updated": await self.catalog.update(entity_id, fields)}
        raise ValueError(f"product не поддерживает op={op!r}")
