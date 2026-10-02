# Changelog

## [Unreleased]

## [0.2.1] — 2026-10-02

### Изменено

- SDK `intelbit-floweon-sdk` `v0.3.0` (PluginRunner с долгоживущим loop — состояние клиентского
  rate limiter сохраняется между вызовами, фактический rps не замерялся; PluginEntrypoint в SDK) (4-17-25).
- Upsert по `code` для `product`, `price`, `store_product` (запись из маппинга пресета без
  `fields` и без `op`); склад остатков — настройка `store_id`. Явный `op` (`delete`/`update`
  без `fields`) — прежний контракт.
- Мок Bitrix24: фильтры каталога/цен/остатков, `create_app(extended=True)` (4 компании
  для сценариев потока A), `GET /_state`; dev-зависимость `python-multipart`.

## [0.2.0] — 2026-10-02

### Добавлено

- Entry point `intelbit.connector.bitrix24` группы `floweon.connectors`: ядро (`floweon run`)
  находит коннектор по `type` из `connectors/*.yaml` пресета (4-17-24).

### Изменено

- Переименование river → floweon (имя продукта Интелбит.Фловеон, D-1 от 21.07.2026):
  пакет `intelbit_river_connector_bitrix24` → `intelbit_floweon_connector_bitrix24`, dist-имя
  `intelbit-river-connector-bitrix24` → `intelbit-floweon-connector-bitrix24`, репозиторий
  `intelbit-river-connector-bitrix24` → `intelbit-floweon-connector-bitrix24`. Прежнее имя продукта — Интелбит:Река.
- Зависимость `intelbit-floweon-sdk` по git-тегу `v0.2.0` (пакет `floweon_sdk`).
- Зависимость `intelbit-bitrix24-client` — по git-тегу `v0.1.0` вместо path `../intelbit-bitrix24-client`;
  CI больше не делает checkout соседнего репозитория.
