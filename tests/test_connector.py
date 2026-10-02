"""Тесты Bitrix24Connector: lifecycle, manifest/capabilities, batch, backoff, subscribe."""

from __future__ import annotations

import httpx
import pytest
from floweon_sdk import ConnectorPlugin
from floweon_sdk.connector import PluginContext

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector
from intelbit_floweon_connector_bitrix24.connector import _MANIFEST
from tests.conftest import MOCK_BASE, make_connector
from tests.mock_bitrix24 import create_app


def test_is_connector_plugin() -> None:
    assert issubclass(Bitrix24Connector, ConnectorPlugin)


def test_manifest_fields() -> None:
    assert _MANIFEST.id == "intelbit.floweon.connector.bitrix24"
    assert _MANIFEST.plugin_type == "connector"
    assert _MANIFEST.license == "Apache-2.0"
    assert Bitrix24Connector.manifest is _MANIFEST


async def test_lifecycle(connector: Bitrix24Connector) -> None:
    await connector.start()
    health = await connector.health_check()
    assert health.healthy is True
    await connector.stop()


async def test_health_unconfigured() -> None:
    transport = httpx.ASGITransport(app=create_app())
    connector = Bitrix24Connector({"webhook_base_url": ""}, _transport=transport)
    health = await connector.health_check()
    assert health.healthy is False
    assert "webhook_base_url" in health.message


async def test_init_rebuilds_from_context(transport: httpx.ASGITransport) -> None:
    connector = make_connector(transport)
    await connector.init(PluginContext({"webhook_base_url": MOCK_BASE, "rate_limit_rps": 1000.0}))
    companies = await connector.read("company", {})
    assert len(companies) == 3


async def test_unknown_entity_read_raises(connector: Bitrix24Connector) -> None:
    with pytest.raises(ValueError, match="Неизвестная сущность"):
        await connector.read("unicorn", {})


async def test_unknown_entity_write_raises(connector: Bitrix24Connector) -> None:
    with pytest.raises(ValueError, match="Неизвестная сущность"):
        await connector.write("unicorn", {"op": "add", "fields": {}})


async def test_batch_call(connector: Bitrix24Connector) -> None:
    out = await connector._client.call_batch(
        {
            "company": ("crm.company.get", {"id": 1}),
            "deal": ("crm.deal.get", {"id": 301}),
        }
    )
    assert out["result"]["company"]["TITLE"] == "ООО Ромашка"
    assert out["result"]["deal"]["TITLE"] == "Поставка №1"


async def test_batch_partial_error(connector: Bitrix24Connector) -> None:
    out = await connector._client.call_batch(
        {
            "ok": ("crm.company.get", {"id": 1}),
            "bad": ("crm.nonexistent.method", {}),
        }
    )
    assert out["result"]["ok"]["ID"] == "1"
    assert "bad" in out["result_error"]


async def test_query_limit_backoff() -> None:
    # Помеченный метод первый раз отдаёт QUERY_LIMIT_EXCEEDED → клиент ретраит и проходит.
    transport = httpx.ASGITransport(app=create_app(limit_methods=frozenset({"crm.company.list"})))
    connector = Bitrix24Connector(
        {"webhook_base_url": MOCK_BASE, "rate_limit_rps": 1000.0},
        _transport=transport,
    )
    companies = await connector.read("company", {})
    assert len(companies) == 3


async def test_subscribe_event(connector: Bitrix24Connector) -> None:
    body = (
        b"event=ONCRMDEALUPDATE&data[FIELDS][ID]=301&ts=1700000000"
        b"&auth[application_token]=out-token"
    )
    event = await connector.subscribe({}, body)
    assert event["entity"] == "deal"
    assert event["idempotency_key"] == "bitrix24:ONCRMDEALUPDATE:301:1700000000"
