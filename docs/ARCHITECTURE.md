# Архитектура коннектора Bitrix24

## Положение во Фловеоне

Коннектор реализует контракт `ConnectorPlugin` из `floweon-sdk` (см. **ADR-006 — Plugin API
contract и SDK**): lifecycle `init/start/stop/health_check/reload` + `read`/`write`, плюс
`subscribe` для приёма исходящих вебхуков коробки.

Целевой обмен описан в **ADR-001 проекта 4-27 «Коннектор SAP и обмен с Bitrix24 через
Фловеон»**: контрагент B24→SAP, каталог/цены/остатки SAP→B24, сделки/резервы — дорожная карта.

## Слои

```
Bitrix24Connector (ConnectorPlugin)
  ├── CompaniesDomain   crm.company.*  + crm.requisite.*
  ├── CatalogDomain     catalog.product.* + catalog.price.*
  ├── StockDomain       catalog.store.* + catalog.storeproduct.*
  ├── DealsDomain       crm.deal.* + crm.deal.productrows.*
  └── Bitrix24WebhookReceiver  (исходящие вебхуки company/deal/contact)
        ↓
  Bitrix24Client  (intelbit-bitrix24-client) — call / call_batch / list_all / rate-limit
```

- `fieldmaps.py` — карты стандартных полей B24 ↔ канонические ключи. Неизвестные поля
  проходят насквозь, чтобы пресет мог дослать своё.
- Бизнес-маппинги направлений и `UF_*` — **в пресетах** (`b24-sap`, `crm-onec`), не здесь.

## Контракт ADR-006

- Idempotent относительно retry; in-memory state между вызовами не держим.
- Клиент открывает/закрывает `httpx.AsyncClient` на каждый запрос (acquire-on-call).
- Payload — JSON-serializable.

## События vs pull

- CRM (company/deal/contact) — есть исходящие вебхуки коробки → `subscribe`.
- Каталог/остатки — надёжных событий у коробки нет → синхронизация **pull** по расписанию
  в пресете. Псевдо-события не реализуются.
