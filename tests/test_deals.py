"""Contract-тесты домена «Сделки»: crm.deal.* + crm.deal.productrows.*."""

from __future__ import annotations

import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector

pytestmark = pytest.mark.contract


async def test_deal_list_paginates(connector: Bitrix24Connector) -> None:
    deals = await connector.read("deal", {})
    assert len(deals) == 3
    assert {d["title"] for d in deals} == {"Поставка №1", "Поставка №2", "Поставка №3"}


async def test_deal_get_maps_fields(connector: Bitrix24Connector) -> None:
    rows = await connector.read("deal", {"id": 301})
    assert rows[0]["id"] == "301"
    assert rows[0]["stage_id"] == "NEW"
    assert rows[0]["opportunity"] == "1000"


async def test_deal_add(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "deal", {"op": "add", "fields": {"title": "Поставка №4", "opportunity": 4000}}
    )
    new_id = res["id"]
    rows = await connector.read("deal", {"id": new_id})
    assert rows[0]["title"] == "Поставка №4"


async def test_deal_update(connector: Bitrix24Connector) -> None:
    res = await connector.write("deal", {"op": "update", "id": 302, "fields": {"stage_id": "WON"}})
    assert res["updated"] is True
    rows = await connector.read("deal", {"id": 302})
    assert rows[0]["stage_id"] == "WON"


async def test_deal_delete(connector: Bitrix24Connector) -> None:
    res = await connector.write("deal", {"op": "delete", "id": 303})
    assert res["deleted"] is True


async def test_productrows_get(connector: Bitrix24Connector) -> None:
    rows = await connector.read("deal_productrows", {"deal_id": 301})
    assert rows[0]["product_id"] == "101"
    assert rows[0]["quantity"] == "10"
    assert rows[0]["measure_code"] == "796"


async def test_productrows_set(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "deal_productrows",
        {
            "deal_id": 302,
            "rows": [
                {"product_id": 102, "product_name": "Гайка М6", "price": 5, "quantity": 4,
                 "measure_code": 796}
            ],
        },
    )
    assert res["updated"] is True
    rows = await connector.read("deal_productrows", {"deal_id": 302})
    assert rows[0]["product_id"] == "102"
    assert rows[0]["quantity"] == "4"
