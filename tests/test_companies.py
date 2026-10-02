"""Contract-тесты домена «Контрагенты»: компании + реквизиты (ИНН/КПП)."""

from __future__ import annotations

import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector

pytestmark = pytest.mark.contract


async def test_company_list_paginates(connector: Bitrix24Connector) -> None:
    companies = await connector.read("company", {})
    assert len(companies) == 3  # 3 записи через 2 страницы (MOCK_PAGE=2)
    assert {c["title"] for c in companies} == {"ООО Ромашка", "ООО Лютик", "ЗАО Пион"}


async def test_company_get_maps_fields(connector: Bitrix24Connector) -> None:
    rows = await connector.read("company", {"id": 1})
    assert rows[0]["id"] == "1"
    assert rows[0]["title"] == "ООО Ромашка"
    assert rows[0]["currency_id"] == "RUB"


async def test_company_add_then_get(connector: Bitrix24Connector) -> None:
    result = await connector.write("company", {"op": "add", "fields": {"title": "Новая"}})
    new_id = result["id"]
    rows = await connector.read("company", {"id": new_id})
    assert rows[0]["title"] == "Новая"


async def test_company_update(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "company", {"op": "update", "id": 2, "fields": {"title": "ООО Лютик-2"}}
    )
    assert res["updated"] is True
    rows = await connector.read("company", {"id": 2})
    assert rows[0]["title"] == "ООО Лютик-2"


async def test_company_delete(connector: Bitrix24Connector) -> None:
    res = await connector.write("company", {"op": "delete", "id": 3})
    assert res["deleted"] is True
    remaining = await connector.read("company", {})
    assert all(c["id"] != "3" for c in remaining)


async def test_company_list_filter_passthrough(connector: Bitrix24Connector) -> None:
    # filter маппится в стандартные поля; мок отдаёт всё — проверяем, что не падает.
    companies = await connector.read("company", {"filter": {"title": "ООО Ромашка"}})
    assert len(companies) == 3


async def test_requisites_inn_kpp(connector: Bitrix24Connector) -> None:
    requisites = await connector.read("requisite", {"company_id": 1})
    assert requisites[0]["inn"] == "7701234567"
    assert requisites[0]["kpp"] == "770101001"
    assert requisites[0]["ogrn"] == "1027700000001"


async def test_get_inn_kpp_helper(connector: Bitrix24Connector) -> None:
    inn_kpp = await connector.companies.get_inn_kpp(1)
    assert inn_kpp == {"inn": "7701234567", "kpp": "770101001"}


async def test_get_inn_kpp_empty(connector: Bitrix24Connector) -> None:
    inn_kpp = await connector.companies.get_inn_kpp(2)  # у компании 2 реквизитов нет
    assert inn_kpp == {"inn": None, "kpp": None}


async def test_requisite_add(connector: Bitrix24Connector) -> None:
    res = await connector.write(
        "requisite", {"op": "add", "fields": {"company_id": 2, "inn": "7799999999"}}
    )
    assert isinstance(res["id"], int)
