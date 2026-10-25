"""Contract-тесты домена «Складские остатки»: catalog.store.* + catalog.storeproduct.*."""

from __future__ import annotations

import httpx
import pytest
from intelbit_bitrix24_client import Bitrix24Error

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector
from tests.conftest import MOCK_BASE, make_connector
from tests.mock_bitrix24 import create_app

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


async def test_stock_explicit_write_absent_on_box(connector: Bitrix24Connector) -> None:
    """catalog.storeproduct.add/update на коробке нет (стенд 4-17-28) — ошибка коробки."""
    with pytest.raises(Bitrix24Error, match="Could not find description of add"):
        await connector.write(
            "store_product",
            {"op": "add", "fields": {"store_id": 201, "product_id": 102, "amount": 50}},
        )


async def test_set_amount_documents(connector: Bitrix24Connector) -> None:
    """Складской учёт: рост — оприходование S, снижение — списание D, равенство — noop."""
    up = await connector.stock.set_amount(201, 101, 130, title="t")
    assert (up["op"], up["doc_type"], up["delta"]) == ("document", "S", 30)
    down = await connector.stock.set_amount(201, 101, 90, title="t")
    assert (down["doc_type"], down["delta"]) == ("D", -40)
    same = await connector.stock.set_amount(201, 101, 90, title="t")
    assert same["op"] == "noop"
    stock = await connector.read("store_product", {"store_id": 201, "product_id": 101})
    assert float(stock[0]["amount"]) == 90


async def test_set_amount_new_row(connector: Bitrix24Connector) -> None:
    """Первое движение товара на складе создаёт строку остатка."""
    await connector.stock.set_amount(201, 102, 7, title="t")
    stock = await connector.read("store_product", {"store_id": 201, "product_id": 102})
    assert float(stock[0]["amount"]) == 7


async def test_set_amount_failed_document_removed(
    connector: Bitrix24Connector, transport: httpx.ASGITransport
) -> None:
    """Сбой позиции документа: непроведённый документ удаляется, ошибка — наружу."""
    async with httpx.AsyncClient(transport=transport, base_url="http://mock-b24") as http:
        await http.post("/_fail", json={"method": "catalog.document.element.add"})
        with pytest.raises(Bitrix24Error):
            await connector.stock.set_amount(201, 101, 130, title="t")
        state = (await http.get("/_state")).json()
    assert state["documents"] == []


async def test_set_amount_without_inventory_mode() -> None:
    """Складской учёт выключен: остаток — quantity товара."""
    connector = make_connector(httpx.ASGITransport(app=create_app(inventory_mode=False)))
    result = await connector.stock.set_amount(201, 101, 12, title="t")
    assert result == {"op": "quantity", "id": 101}
    product = await connector.read("product", {"id": 101})
    assert str(product[0]["quantity"]) == "12"


async def test_set_amount_requires_responsible(transport: httpx.ASGITransport) -> None:
    """Без ответственного документ не создать (коробка: Required fields: responsibleId)."""
    connector = Bitrix24Connector(
        {"webhook_base_url": MOCK_BASE, "rate_limit_rps": 1000.0, "event_secret": "s"},
        _transport=transport,
    )
    with pytest.raises(ValueError, match="documents_responsible_id"):
        await connector.stock.set_amount(201, 101, 1, title="t")
