"""TLS коннектора: ca_bundle / verify_ssl / allow_insecure_tls → клиент Bitrix24."""

from __future__ import annotations

import logging
import ssl
from pathlib import Path
from typing import Any

import pytest

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector, ConfigurationError
from tests.conftest import MOCK_BASE, TEST_EVENT_SECRET


def _config(**extra: Any) -> dict[str, Any]:
    return {"webhook_base_url": MOCK_BASE, "event_secret": TEST_EVENT_SECRET, **extra}


def _ca_file(tmp_path: Path) -> str:
    import certifi

    path = tmp_path / "ca.pem"
    path.write_text(Path(certifi.where()).read_text())
    return str(path)


def test_default_verifies() -> None:
    assert Bitrix24Connector(_config())._client._verify is True


def test_ca_bundle_passed_to_client(tmp_path: Path) -> None:
    connector = Bitrix24Connector(_config(ca_bundle=_ca_file(tmp_path), verify_ssl=False))
    assert isinstance(connector._client._verify, ssl.SSLContext)


def test_empty_ca_bundle_ignored() -> None:
    assert Bitrix24Connector(_config(ca_bundle=""))._client._verify is True


def test_missing_ca_bundle_file() -> None:
    with pytest.raises(ConfigurationError, match="CA не найден"):
        Bitrix24Connector(_config(ca_bundle="/nonexistent/ca.pem"))


@pytest.mark.parametrize("value", [False, "false", "0"])
def test_insecure_requires_flag(value: Any) -> None:
    with pytest.raises(ConfigurationError, match="allow_insecure_tls"):
        Bitrix24Connector(_config(verify_ssl=value))


def test_insecure_with_flag_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        connector = Bitrix24Connector(_config(verify_ssl="false", allow_insecure_tls="true"))
    assert connector._client._verify is False
    assert "ОТКЛЮЧЕНА" in caplog.text
    assert TEST_EVENT_SECRET not in caplog.text
