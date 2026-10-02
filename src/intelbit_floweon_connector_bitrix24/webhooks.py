"""Приём исходящих вебхуков коробки Bitrix24 → канонический Event.

Коробка шлёт события CRM как `application/x-www-form-urlencoded`::

    event=ONCRMDEALUPDATE&data[FIELDS][ID]=42&ts=1700000000
    &auth[application_token]=TOKEN&auth[domain]=portal.bitrix24.ru

Каталог/остатки надёжных событий не имеют → синхронизация pull (по расписанию
в пресете). Здесь — только company/deal/contact.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl

# Событие коробки → (каноническая сущность, действие).
_EVENT_MAP: dict[str, tuple[str, str]] = {
    "ONCRMCOMPANYADD": ("company", "add"),
    "ONCRMCOMPANYUPDATE": ("company", "update"),
    "ONCRMCOMPANYDELETE": ("company", "delete"),
    "ONCRMDEALADD": ("deal", "add"),
    "ONCRMDEALUPDATE": ("deal", "update"),
    "ONCRMDEALDELETE": ("deal", "delete"),
    "ONCRMCONTACTADD": ("contact", "add"),
    "ONCRMCONTACTUPDATE": ("contact", "update"),
}


class WebhookValidationError(RuntimeError):
    """Исходящий вебхук не прошёл проверку (неизвестное событие или secret)."""


def _unflatten(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """`data[FIELDS][ID]=42` → {"data": {"FIELDS": {"ID": "42"}}}."""
    root: dict[str, Any] = {}
    for raw_key, value in pairs:
        head, _, rest = raw_key.partition("[")
        keys = [head]
        if rest:
            keys += [seg.rstrip("]") for seg in rest.split("[")]
        node = root
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
    return root


class Bitrix24WebhookReceiver:
    """Парсинг и валидация исходящих вебхуков коробки Bitrix24."""

    def __init__(self, event_secret: str | None = None) -> None:
        self._secret = event_secret

    def parse_event(self, body: bytes) -> dict[str, Any]:
        """Form-тело события → канонический Event с детерминированным idempotency-key."""
        parsed = _unflatten(parse_qsl(body.decode("utf-8")))

        event_name = str(parsed.get("event", "")).upper()
        if event_name not in _EVENT_MAP:
            raise WebhookValidationError(f"Неизвестное событие Bitrix24: {event_name!r}")

        self._verify_secret(parsed)

        entity, action = _EVENT_MAP[event_name]
        data = parsed.get("data")
        fields = data.get("FIELDS", {}) if isinstance(data, dict) else {}
        entity_id = str(fields.get("ID", ""))
        ts = str(parsed.get("ts", ""))

        return {
            "event": event_name,
            "entity": entity,
            "action": action,
            "entity_id": entity_id,
            "idempotency_key": f"bitrix24:{event_name}:{entity_id}:{ts}",
            "raw": parsed,
        }

    def _verify_secret(self, parsed: dict[str, Any]) -> None:
        if not self._secret:
            return
        auth = parsed.get("auth", {}) if isinstance(parsed.get("auth"), dict) else {}
        if auth.get("application_token") != self._secret:
            raise WebhookValidationError("Неверный application_token в исходящем вебхуке")
