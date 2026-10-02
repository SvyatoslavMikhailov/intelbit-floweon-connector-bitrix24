"""Фикстуры contract-тестов: свежий FastAPI-мок Bitrix24 через ASGITransport."""

from __future__ import annotations

import httpx
import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector
from tests.mock_bitrix24 import create_app

MOCK_BASE = "http://mock-b24/rest/1/tok42/"


def make_connector(transport: httpx.ASGITransport) -> Bitrix24Connector:
    return Bitrix24Connector(
        {
            "webhook_base_url": MOCK_BASE,
            "iblock_id": 14,
            "price_type_id": 1,
            "rate_limit_rps": 1000.0,
            "event_secret": "out-token",
        },
        _transport=transport,
    )


@pytest.fixture
def transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=create_app())


@pytest.fixture
def connector(transport: httpx.ASGITransport) -> Bitrix24Connector:
    return make_connector(transport)
