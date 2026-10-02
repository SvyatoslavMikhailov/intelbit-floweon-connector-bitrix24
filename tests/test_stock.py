"""Contract-тесты домена «Складские остатки»: catalog.store.* + catalog.storeproduct.*."""

from __future__ import annotations

import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector

pytestmark = pytest.mark.contract


async def test_store_list(connector: Bitrix24Connector) -> None:
    stores = await connector.read("store", {})
    assert stores[0]["id"] == 201
    assert stores[0]["title"] == "Главный склад"
    assert stores[0]["address"] == "Москва"


async def test_store_get(connector: Bitrix24Connector) -> None:
    rows = await connector.read("store", {"id": 201})
    assert rows[0]["title"] == "Главный склад"


async def test_stock_list_maps_fields(connector: Bitrix24Connector) -> None:
    stock = await connector.read("store_product", {"store_id": 201, "product_id": 101})
    assert stock[0]["store_id"] == 201
    assert stock[0]["product_id"] == 101
    assert stock[0]["amount"] == 100
    assert stock[0]["quantity_reserved"] == 5


async def test_stock_add(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "store_product",
        {"op": "add", "fields": {"store_id": 201, "product_id": 102, "amount": 50}},
    )
    assert isinstance(res["id"], int)


async def test_stock_update(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "store_product", {"op": "update", "id": 5001, "fields": {"amount": 90}}
    )
    assert res["updated"] is True
    stock = await connector.stock.get_stock(5001)
    assert str(stock["amount"]) == "90"  # запись через form round-trip'ится строкой
