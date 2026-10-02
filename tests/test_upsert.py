"""Upsert по code (пресет b24-sap, 4-17-25) и расширенный мок."""

from __future__ import annotations

import httpx
import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector
from tests.conftest import MOCK_BASE, TEST_EVENT_SECRET
from tests.mock_bitrix24 import create_app


def _connector(transport: httpx.ASGITransport, **extra: object) -> Bitrix24Connector:
    return Bitrix24Connector(
        {
            "webhook_base_url": MOCK_BASE,
            "iblock_id": 14,
            "price_type_id": 1,
            "rate_limit_rps": 1000.0,
            "event_secret": TEST_EVENT_SECRET,
            **extra,
        },
        _transport=transport,
    )


@pytest.fixture
def ext_transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=create_app(extended=True))


async def _state(transport: httpx.ASGITransport) -> dict[str, object]:
    async with httpx.AsyncClient(transport=transport, base_url="http://mock-b24") as client:
        response = await client.get("/_state")
    return response.json()  # type: ignore[no-any-return]


class TestProductUpsert:
    async def test_add_then_update_same_code(self, ext_transport: httpx.ASGITransport) -> None:
        connector = _connector(ext_transport)
        first = await connector.write(
            "product",
            {
                "code": "100",
                "name": "Болт",
                "measure": "ST",
                "_mode": "x",
                "_idempotency_key": "k",
                "detail_text": None,
            },
        )
        assert first["op"] == "add"
        second = await connector.write("product", {"code": "100", "name": "Болт М6"})
        assert second == {"id": first["id"], "op": "update", "code": "100"}

        products = (await _state(ext_transport))["products"]
        assert isinstance(products, list) and len(products) == 1
        product = products[0]
        assert product["name"] == "Болт М6"
        assert product["code"] == "100"
        # Служебные ключи ядра и None в Bitrix24 не уходят.
        assert not any(str(k).startswith("_") for k in product)
        assert "detailText" not in product

    async def test_code_required(self, ext_transport: httpx.ASGITransport) -> None:
        with pytest.raises(ValueError, match="code"):
            await _connector(ext_transport).write("product", {"name": "без кода"})


class TestPriceAndStockUpsert:
    async def test_price_via_code(self, ext_transport: httpx.ASGITransport) -> None:
        connector = _connector(ext_transport)
        product = await connector.write("product", {"code": "101", "name": "Гайка"})
        added = await connector.write("price", {"code": "101", "price": 7.0, "currency": "RUB"})
        updated = await connector.write("price", {"code": "101", "price": 8.5, "currency": "RUB"})
        assert added["op"] == "add"
        assert updated == {"id": added["id"], "op": "update", "code": "101"}
        prices = (await _state(ext_transport))["prices"]
        assert isinstance(prices, list) and len(prices) == 1
        assert float(prices[0]["price"]) == 8.5
        assert str(prices[0]["productId"]) == str(product["id"])
        assert str(prices[0]["catalogGroupId"]) == "1"

    async def test_price_unknown_product(self, ext_transport: httpx.ASGITransport) -> None:
        with pytest.raises(ValueError, match="не найден"):
            await _connector(ext_transport).write("price", {"code": "999", "price": 1})

    async def test_store_product_via_code(self, ext_transport: httpx.ASGITransport) -> None:
        connector = _connector(ext_transport, store_id="201")
        product = await connector.write("product", {"code": "100", "name": "Болт"})
        added = await connector.write("store_product", {"code": "100", "amount": 170})
        updated = await connector.write("store_product", {"code": "100", "amount": 150})
        assert added["op"] == "add"
        assert updated["op"] == "update"
        rows = (await _state(ext_transport))["storeproducts"]
        assert isinstance(rows, list) and len(rows) == 1
        assert str(rows[0]["storeId"]) == "201"
        assert str(rows[0]["productId"]) == str(product["id"])
        assert str(rows[0]["amount"]) == "150"

    async def test_store_id_required(self, ext_transport: httpx.ASGITransport) -> None:
        connector = _connector(ext_transport)
        await connector.write("product", {"code": "100", "name": "Болт"})
        with pytest.raises(ValueError, match="store_id"):
            await connector.write("store_product", {"code": "100", "amount": 1})

    async def test_legacy_fields_contract_kept(self, connector: Bitrix24Connector) -> None:
        result = await connector.write("product", {"op": "add", "fields": {"name": "Новый"}})
        assert "id" in result


class TestExtendedMock:
    async def test_companies_and_requisites(self, ext_transport: httpx.ASGITransport) -> None:
        connector = _connector(ext_transport)
        company = (await connector.read("company", {"id": 2}))[0]
        assert company["title"] == "ООО Лютик"
        assert company["address_city"] == "Санкт-Петербург"
        requisites = await connector.read("requisite", {"company_id": 2})
        assert [(r["inn"], r["kpp"]) for r in requisites] == [("7702000002", "770201001")]
        assert await connector.read("requisite", {"company_id": 3}) == []

    async def test_catalog_empty_store_present(self, ext_transport: httpx.ASGITransport) -> None:
        state = await _state(ext_transport)
        assert state["products"] == []
        assert [s["id"] for s in state["stores"]] == [201]  # type: ignore[union-attr]

    async def test_product_list_filter(self, transport: httpx.ASGITransport) -> None:
        connector = _connector(transport)
        await connector.write("product", {"op": "update", "id": 102, "fields": {"code": "G6"}})
        found = await connector.read("product", {"filter": {"code": "G6"}})
        assert [p["id"] for p in found] == [102]
        assert await connector.read("product", {"filter": {"code": "none"}}) == []

    async def test_stock_and_price_filters(self, transport: httpx.ASGITransport) -> None:
        connector = _connector(transport)
        assert len(await connector.read("store_product", {"store_id": 201, "product_id": 101})) == 1
        assert await connector.read("store_product", {"store_id": 201, "product_id": 102}) == []
        assert len(await connector.read("price", {"product_id": 101})) == 1
        assert await connector.read("price", {"product_id": 103}) == []


class TestLegacyContract:
    async def test_explicit_op_without_fields_not_upsert(
        self, transport: httpx.ASGITransport
    ) -> None:
        """op без fields — прежний контракт, а не upsert по code (регрессия 4-17-25)."""
        connector = _connector(transport)
        result = await connector.write("product", {"op": "update", "id": 101})
        assert "updated" in result
