"""Лиды, субъект события, банковские реквизиты, товары по свойству (4-17-30)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector
from intelbit_floweon_connector_bitrix24.domains.properties import (
    PROPERTY_WRITE_LOST,
    property_field,
    property_value,
)
from tests.conftest import MOCK_BASE, TEST_EVENT_SECRET
from tests.mock_bitrix24 import create_app

PROPS = {"ref": "PROPERTY_61", "current_material": "property62"}


@pytest.fixture
def transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=create_app(extended=True))


def _connector(transport: httpx.ASGITransport, **extra: Any) -> Bitrix24Connector:
    return Bitrix24Connector(
        {
            "webhook_base_url": MOCK_BASE,
            "iblock_id": 14,
            "rate_limit_rps": 1000.0,
            "event_secret": TEST_EVENT_SECRET,
            "store_id": 201,
            "documents_responsible_id": 1,
            "product_properties": PROPS,
            **extra,
        },
        _transport=transport,
    )


async def _products(transport: httpx.ASGITransport) -> dict[int, dict[str, Any]]:
    async with httpx.AsyncClient(transport=transport, base_url="http://mock-b24") as client:
        state = (await client.get("/_state")).json()
    return {int(p["id"]): p for p in state["products"]}


def test_property_helpers() -> None:
    assert property_field("PROPERTY_61") == property_field("61") == "property61"
    with pytest.raises(ValueError, match="PROPERTY_<ID>"):
        property_field("REF")
    assert property_value({"valueId": 1, "value": " R-1 "}) == "R-1"
    assert property_value([{"value": "R-2"}]) == "R-2"
    assert property_value(None) == ""


class TestSubject:
    async def test_lead_semantics_and_company(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport)
        (s,) = await c.read("subject", {"entity": "lead", "entity_id": "502"})
        assert s == {
            "source": "lead",
            "company_id": "2",
            "lead_id": "502",
            "lead_semantics": "S",
            "entity": "company",
            "entity_id": "2",
        }
        (s,) = await c.read("subject", {"entity": "lead", "entity_id": "501"})
        assert s["lead_semantics"] == "P"
        (s,) = await c.read("subject", {"entity": "lead", "entity_id": "505"})
        assert (s["company_id"], s["entity"], s["entity_id"]) == ("", "lead", "505")

    async def test_requisite_and_bankdetail_resolve_company(
        self, transport: httpx.ASGITransport
    ) -> None:
        c = _connector(transport)
        (s,) = await c.read("subject", {"entity": "requisite", "entity_id": "12"})
        assert (s["company_id"], s["lead_id"]) == ("2", "")
        (s,) = await c.read("subject", {"entity": "bankdetail", "entity_id": "21"})
        assert s["company_id"] == "1"

    async def test_bank_details_of_inn_requisite(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport)
        banks = await c.read("bank_detail", {"company_id": 1})
        assert [(b["bik"], b["account"]) for b in banks] == [
            ("044525225", "40702810400000000001"),
            ("044525593", "40702810500000000002"),
        ]
        assert await c.read("bank_detail", {"company_id": 5}) == []

    async def test_webhook_lead_and_bankdetail_events(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport)
        for name, entity in (("ONCRMLEADUPDATE", "lead"), ("ONCRMBANKDETAILADD", "bankdetail")):
            body = (
                f"event={name}&data[FIELDS][ID]=7&ts=1&auth[application_token]={TEST_EVENT_SECRET}"
            ).encode()
            event = await c.subscribe({}, body)
            assert (event["entity"], event["entity_id"]) == (entity, "7")


class TestPropertySync:
    async def test_sync_only_changes_and_reports(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport)
        items = [
            {"ref": "R-100", "matnr": "M1002"},
            {"ref": "R-200", "matnr": "M2002"},
            {"ref": "R-400", "matnr": "M4001"},
        ]
        data = {
            "key_property": "ref",
            "value_property": "current_material",
            "key_field": "ref",
            "value_field": "matnr",
            "items": items,
        }
        first = await c.write("product_property_sync", data)
        assert [(x["key"], x["old"], x["new"]) for x in first["changed"]] == [
            ("R-100", "", "M1002"),
            ("R-200", "", "M2002"),
        ]
        assert first["without_value"] == ["R-300 — товар 603 «Зонд В»"]
        assert first["missing"] == {"count": 1, "sample": ["R-400"]}
        products = await _products(transport)
        assert products[601]["property62"]["value"] == "M1002"
        assert products[604]["property62"] is None  # без REF — не тронут

        items[0]["matnr"] = "M1003"
        second = await c.write("product_property_sync", data)
        assert [(x["key"], x["old"], x["new"]) for x in second["changed"]] == [
            ("R-100", "M1002", "M1003")
        ]
        assert second["unchanged"] == 1

    async def test_unconfigured_property(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport, product_properties={"ref": "PROPERTY_61", "current_material": ""})
        with pytest.raises(ValueError, match="current_material"):
            await c.write(
                "product_property_sync",
                {"key_property": "ref", "value_property": "current_material", "items": []},
            )

    async def test_write_lost_detected(
        self, transport: httpx.ASGITransport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c = _connector(transport)
        original = c.catalog.update

        async def as_string(product_id: int, data: dict[str, Any]) -> bool:
            # Строка вместо объекта — коробка молча обнуляет свойство.
            return await original(product_id, {k: v["value"] for k, v in data.items()})

        monkeypatch.setattr(c.catalog, "update", as_string)
        with pytest.raises(ValueError, match=PROPERTY_WRITE_LOST):
            await c.write(
                "product_property_sync",
                {
                    "key_property": "ref",
                    "value_property": "current_material",
                    "items": [{"key": "R-100", "value": "M1002"}],
                },
            )


class TestStockAndUpsertByProperty:
    async def test_stock_only_current_material(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport)
        await c.write(
            "product_property_sync",
            {
                "key_property": "ref",
                "value_property": "current_material",
                "items": [{"key": "R-100", "value": "M1002"}],
            },
        )
        result = await c.write(
            "store_product_sync",
            {
                "key_property": "current_material",
                "scope_property": "ref",
                "items": [
                    {"code": "M1001", "amount": 5},  # нетекущий материал R-100 — не ошибка
                    {"code": "M1002", "amount": 7},
                ],
            },
        )
        assert result["written"] == 1
        # Товары с REF без текущего материала; 604 без REF — не в списке.
        assert result["without_key"] == [
            "R-200 — товар 602 «Зонд Б»",
            "R-300 — товар 603 «Зонд В»",
        ]
        stock = await c.read("store_product", {"store_id": 201, "product_id": 601})
        assert float(stock[0]["amount"]) == 7.0

    async def test_upsert_by_property_no_duplicates(self, transport: httpx.ASGITransport) -> None:
        c = _connector(transport)
        data = {
            "key_property": "ref",
            "key": "R-400",
            "name": "Зонд Г",
            "properties": {"current_material": "M4001"},
        }
        first = await c.write("product_by_property", data)
        assert first["op"] == "add"
        again = await c.write("product_by_property", data)
        assert again == {"id": first["id"], "op": "unchanged"}
        data["properties"] = {"current_material": "M4002"}
        assert (await c.write("product_by_property", data))["op"] == "update"
        products = await _products(transport)
        refs = [p for p in products.values() if (p.get("property61") or {}).get("value") == "R-400"]
        assert len(refs) == 1 and refs[0]["property62"]["value"] == "M4002"
        assert refs[0]["name"] == "Зонд Г"
