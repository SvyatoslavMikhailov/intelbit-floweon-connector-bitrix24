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

_MANIFEST = PluginManifest(
    id="intelbit.floweon.connector.bitrix24",
    version="0.2.0",
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
        """Записать сущность. `data.op` ∈ {add, update, delete}; поля — в `data.fields`."""
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
