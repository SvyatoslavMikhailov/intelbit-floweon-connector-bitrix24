"""Тесты приёма исходящих вебхуков коробки → канонический Event."""

from __future__ import annotations

import pytest

from intelbit_floweon_connector_bitrix24 import (
    Bitrix24WebhookReceiver,
    ConfigurationError,
    WebhookValidationError,
)


def _body(event: str, entity_id: str, ts: str = "1700000000", token: str = "out-token") -> bytes:
    return (
        f"event={event}"
        f"&data[FIELDS][ID]={entity_id}"
        f"&ts={ts}"
        f"&auth[application_token]={token}"
        f"&auth[domain]=portal.bitrix24.ru"
    ).encode()


def test_company_update_event() -> None:
    receiver = Bitrix24WebhookReceiver("out-token")
    event = receiver.parse_event(_body("ONCRMCOMPANYUPDATE", "42"))
    assert event["entity"] == "company"
    assert event["action"] == "update"
    assert event["entity_id"] == "42"
    assert event["idempotency_key"] == "bitrix24:ONCRMCOMPANYUPDATE:42:1700000000"


def test_deal_add_event() -> None:
    receiver = Bitrix24WebhookReceiver("out-token")
    event = receiver.parse_event(_body("ONCRMDEALADD", "301"))
    assert event["entity"] == "deal"
    assert event["action"] == "add"


def test_idempotency_key_is_stable() -> None:
    receiver = Bitrix24WebhookReceiver("out-token")
    a = receiver.parse_event(_body("ONCRMDEALUPDATE", "7"))
    b = receiver.parse_event(_body("ONCRMDEALUPDATE", "7"))
    assert a["idempotency_key"] == b["idempotency_key"]


def test_unknown_event_rejected() -> None:
    receiver = Bitrix24WebhookReceiver("out-token")
    with pytest.raises(WebhookValidationError, match="Неизвестное событие"):
        receiver.parse_event(_body("ONSOMETHINGWEIRD", "1"))


def test_bad_secret_rejected() -> None:
    receiver = Bitrix24WebhookReceiver("out-token")
    with pytest.raises(WebhookValidationError, match="application_token"):
        receiver.parse_event(_body("ONCRMCOMPANYADD", "1", token="wrong"))


@pytest.mark.parametrize("secret", [None, ""])
def test_no_secret_fails_closed(secret: str | None) -> None:
    with pytest.raises(ConfigurationError, match="event_secret"):
        Bitrix24WebhookReceiver(secret)


def test_missing_token_rejected() -> None:
    # Проверка выполняется всегда: тело без auth[application_token] отклоняется.
    receiver = Bitrix24WebhookReceiver("out-token")
    body = b"event=ONCRMCONTACTUPDATE&data[FIELDS][ID]=9&ts=1"
    with pytest.raises(WebhookValidationError, match="application_token"):
        receiver.parse_event(body)


def test_secret_not_leaked_in_errors() -> None:
    secret = "super-secret-token-value"
    receiver = Bitrix24WebhookReceiver(secret)
    with pytest.raises(WebhookValidationError) as exc_info:
        receiver.parse_event(_body("ONCRMCOMPANYADD", "1", token="wrong"))
    assert secret not in str(exc_info.value)
