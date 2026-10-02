# intelbit-floweon-connector-bitrix24

Коннектор **Bitrix24 (коробка)** для платформы **Интелбит.Фловеон**. Обмен по REST-сервису
входящего вебхука по четырём доменам со **стандартными полями** Bitrix24:

| Домен | Сущности | Методы Bitrix24 |
|-------|----------|-----------------|
| Контрагенты | `company`, `requisite` | `crm.company.*`, `crm.requisite.*` (ИНН/КПП) |
| Материалы и цены | `product`, `price` | `catalog.product.*`, `catalog.price.*` |
| Складские остатки | `store`, `store_product` | `catalog.store.*`, `catalog.storeproduct.*` |
| Сделки | `deal`, `deal_productrows` | `crm.deal.*`, `crm.deal.productrows.*` |

Коннектор **preset-agnostic**: бизнес-маппинги направлений (`b24-sap`, `crm-onec`) и
пользовательские поля `UF_*` — в пресетах, не здесь.

## Возможности

- **read** — list (с пагинацией `start/next/total`) и get по 4 доменам.
- **write** — add/update/delete стандартных полей; товарные строки сделки (`set`).
- **subscribe** — приём исходящих вебхуков коробки (`ONCRMCOMPANY*`, `ONCRMDEAL*`,
  `ONCRMCONTACT*`) → канонический Event с idempotency-key.
- Для каталога/остатков надёжных событий у коробки нет → синхронизация **pull**
  (по расписанию в пресете).

Построен на общем Apache-клиенте [`intelbit-bitrix24-client`](https://github.com/SvyatoslavMikhailov/intelbit-bitrix24-client)
и SDK [`intelbit-floweon-sdk`](https://github.com/SvyatoslavMikhailov/intelbit-floweon-sdk)
(оба — публичные git-теги в `[tool.uv.sources]`).

## Конфигурация

См. `src/intelbit_floweon_connector_bitrix24/config_schema.json` и `docs/CONFIGURATION.md`.

```python
from intelbit_floweon_connector_bitrix24 import Bitrix24Connector

connector = Bitrix24Connector({
    "webhook_base_url": "https://portal.bitrix24.ru/rest/1/xxxxxxxx/",
    "iblock_id": 14,
    "price_type_id": 1,
    "rate_limit_rps": 2,
    "event_secret": "<application token исходящего вебхука>",
})

companies = await connector.read("company", {"filter": {"title": "Ромашка"}})
await connector.write("deal", {"op": "add", "fields": {"title": "Новая сделка"}})
```

**Fail-closed вебхуков.** `event_secret` обязателен: без него (или с пустой строкой)
коннектор бросает `ConfigurationError` при создании и при `init()`. Каждый входящий
вебхук проверяется по `auth[application_token]` (сравнение за постоянное время).

## Разработка

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy
uv run pytest
```

CI (`.github/workflows/ci.yml`) ставит зависимости из публичных git-тегов
(`intelbit-bitrix24-client` v0.1.0, `intelbit-floweon-sdk` v0.2.0) и гоняет
ruff + mypy(strict) + pytest.
