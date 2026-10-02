"""Коннектор Bitrix24 (CRM + Торговый каталог) для Интелбит.Фловеон."""

from intelbit_floweon_connector_bitrix24.connector import Bitrix24Connector
from intelbit_floweon_connector_bitrix24.webhooks import (
    Bitrix24WebhookReceiver,
    ConfigurationError,
    WebhookValidationError,
)

__version__ = "0.2.1"

__all__ = [
    "Bitrix24Connector",
    "Bitrix24WebhookReceiver",
    "ConfigurationError",
    "WebhookValidationError",
]
