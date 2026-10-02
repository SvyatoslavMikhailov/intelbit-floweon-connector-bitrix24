# Конфигурация коннектора Bitrix24

Схема — `src/intelbit_floweon_connector_bitrix24/config_schema.json`.

| Параметр | Тип | Обяз. | Назначение |
|----------|-----|:-----:|------------|
| `webhook_base_url` | string (uri) | да | URL входящего вебхука коробки: `https://<portal>/rest/<user_id>/<token>/` |
| `iblock_id` | int | нет | ID инфоблока торгового каталога (для `catalog.*`) |
| `price_type_id` | int | нет | ID типа цены (`catalog.priceType`) для чтения/записи цен |
| `rate_limit_rps` | number | нет | Лимит запросов в секунду (по умолчанию 2) |
| `timeout` | number | нет | Таймаут HTTP-запроса, сек (по умолчанию 30) |
| `event_secret` | string | **да** | `application_token` для проверки исходящих вебхуков (без него — `ConfigurationError`) |

## Пример

```yaml
webhook_base_url: "https://portal.bitrix24.ru/rest/1/xxxxxxxxxxxxxxxx/"
iblock_id: 14
price_type_id: 1
rate_limit_rps: 2
timeout: 30
event_secret: "outgoing-webhook-application-token"
```

## Допущения по стенду

- В коробке Bitrix24 включён модуль **«Торговый каталог»** — обязателен для `catalog.*`
  (товары, цены, склады, остатки).
- Коробка поддерживает **входящие и исходящие вебхуки** без подписки Marketplace.
- Авторизация — через токен, встроенный в URL входящего вебхука. OAuth/Marketplace — v1.1.

## Авторизация исходящих вебхуков

Коробка шлёт исходящие события с `auth[application_token]`. `event_secret` обязателен
(fail-closed): без него коннектор не инициализируется (`ConfigurationError`), а каждое
событие с отсутствующим или несовпадающим токеном отклоняется.
