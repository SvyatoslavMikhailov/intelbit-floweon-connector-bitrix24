"""Contract-тесты домена «Материалы и цены»: catalog.product.* + catalog.price.*."""

from __future__ import annotations

import httpx
import pytest
from intelbit_bitrix24_client import Bitrix24Client, Bitrix24Error

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector
from tests.conftest import MOCK_BASE

pytestmark = pytest.mark.contract


async def test_product_list_paginates_wrapped(connector: Bitrix24Connector) -> None:
    products = await connector.read("product", {})
    assert len(products) == 3  # result.products через 2 страницы
    assert {p["name"] for p in products} == {"Болт М6", "Гайка М6", "Шайба 6"}


async def test_product_get_maps_camel(connector: Bitrix24Connector) -> None:
    rows = await connector.read("product", {"id": 101})
    assert rows[0]["id"] == 101
    assert rows[0]["iblock_id"] == 14
    assert rows[0]["name"] == "Болт М6"


async def test_product_add_uses_iblock(connector: Bitrix24Connector) -> None:
    res = await connector.write("product", {"op": "add", "fields": {"name": "Винт М8"}})
    new_id = res["id"]
    rows = await connector.read("product", {"id": new_id})
    assert rows[0]["name"] == "Винт М8"
    assert str(rows[0]["iblock_id"]) == "14"  # iblock_id из конфига подставлен


async def test_product_update(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "product", {"op": "update", "id": 102, "fields": {"name": "Гайка М8"}}
    )
    assert res["updated"] is True
    rows = await connector.read("product", {"id": 102})
    assert rows[0]["name"] == "Гайка М8"


async def test_price_list(connector: Bitrix24Connector) -> None:
    prices = await connector.read("price", {"product_id": 101})
    assert prices[0]["product_id"] == 101
    assert prices[0]["catalog_group_id"] == 1
    assert prices[0]["currency"] == "RUB"


async def test_price_add_uses_price_type(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "price", {"op": "add", "fields": {"product_id": 102, "price": 7.0, "currency": "RUB"}}
    )
    assert isinstance(res["id"], int)
    prices = await connector.read("price", {})
    assert any(str(p["price"]) == "7.0" for p in prices)


async def test_price_update(connector: Bitrix24Connector) -> None:
    res = await connector.write("price", {"op": "update", "id": 1001, "fields": {"price": 13.0}})
    assert res["updated"] is True


async def test_price_types(connector: Bitrix24Connector) -> None:
    types = await connector.catalog.price_types()
    assert types[0]["name"] == "BASE"


async def test_product_list_select_always_has_required(connector: Bitrix24Connector) -> None:
    """Коробка требует id и iblockId в select (стенд 4-17-28) — коннектор добавляет их сам."""
    rows = await connector.read("product", {"select": ["name"]})
    assert rows and {"id", "iblock_id", "name"} <= set(rows[0])


async def test_product_list_without_select_fails_on_box(transport: httpx.ASGITransport) -> None:
    """Мок повторяет коробку: list без select — ошибка «Required select fields»."""
    client = Bitrix24Client(MOCK_BASE, rps=1000.0, _transport=transport)
    with pytest.raises(Bitrix24Error, match="Required select fields: id, iblockId"):
        await client.call("catalog.product.list", {"filter": {"iblockId": 14}})


async def test_price_add_returns_id_from_price_key(transport: httpx.ASGITransport) -> None:
    """catalog.price.add отвечает {price: {...}}, а не {element: {...}}."""
    client = Bitrix24Client(MOCK_BASE, rps=1000.0, _transport=transport)
    env = await client.call(
        "catalog.price.add",
        {"fields": {"productId": 102, "catalogGroupId": 1, "price": 3, "currency": "RUB"}},
    )
    assert set(env["result"]) == {"price"}
