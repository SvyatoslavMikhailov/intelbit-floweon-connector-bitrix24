# Changelog

## [Unreleased]

### Изменено

- Переименование river → floweon (имя продукта Интелбит.Фловеон, D-1 от 21.07.2026):
  пакет `intelbit_river_connector_bitrix24` → `intelbit_floweon_connector_bitrix24`, dist-имя
  `intelbit-river-connector-bitrix24` → `intelbit-floweon-connector-bitrix24`, репозиторий
  `intelbit-river-connector-bitrix24` → `intelbit-floweon-connector-bitrix24`. Прежнее имя продукта — Интелбит:Река.
- Зависимость `intelbit-floweon-sdk` по git-тегу `v0.2.0` (пакет `floweon_sdk`).
- Зависимость `intelbit-bitrix24-client` — по git-тегу `v0.1.0` вместо path `../intelbit-bitrix24-client`;
  CI больше не делает checkout соседнего репозитория.
