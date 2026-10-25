# Changelog

## [Unreleased]

## [0.3.1] — 2026-10-25

Расхождения мока с реальной коробкой «Корпоративный портал» 26.800 (BitrixVM, стенд
4-17-28). Коннектор приведён к коробке, мок — к коннектору и коробке.

### Исправлено

- `catalog.product.list`: коробка требует `id` и `iblockId` в `select` («Required select
  fields») — upsert по `code` падал на поиске товара. Select по умолчанию — стандартные
  поля, обязательные добавляются всегда. Поле `xml_id` ↔ `xmlId`.
- `catalog.price.add/update` отвечают под ключом `price`, а не `element` — id записи
  берётся из любой обёртки ответа.
- Остатки: `catalog.storeproduct.add/update` на коробке нет. При складском учёте
  (`catalog.document.mode.status` = `Y`) upsert `store_product` доводит остаток
  документом: разница с текущим → оприходование `S` или списание `D`, проведение
  `conduct`, при сбое непроведённый документ удаляется; без изменений — `noop`. Без
  учёта — `quantity` товара. Новые ключи конфига: `documents_responsible_id`
  (обязателен для документов, иначе «Required fields: responsibleId»),
  `document_currency` (по умолчанию RUB). Заголовок документа — «Фловеон: остаток <code>».
- Upsert `store_product`: пустой `amount` — ошибка (раньше 0 → документ списания обнулял
  склад); товар без карточки — `ValueError` с меткой `product_not_found: …` (для
  `on_error_match` пресета). Откат непроведённого документа — при любом исключении,
  включая отмену. `select` товара по умолчанию — все поля `fieldmaps.PRODUCT`.
- Реквизиты: коробка сама создаёт пустой реквизит вместе с компанией — `read requisite`
  отдаёт реквизиты с ИНН первыми.
- Нотификатор: v3-чат задачи при вебхуке без scope `tasks`
  (`…INSUFFICIENTSCOPEEXCEPTION` или `insufficient_scope`; `tasks.task.*` v2 при этом работают со scope `task`)
  откатывается на форум задачи с причиной в health (`comments_channel=forum (…)`) и предупреждением в лог при первом откате (health наружу не виден).

### Мок

- `catalog.product.list` без `select` — ошибка коробки; `catalog.price.*` → `price`;
  `catalog.storeproduct.add/update` — ошибка 22002; документы `catalog.document.*`
  (`create_app(inventory_mode=True)` по умолчанию); `crm.company.add` и e2e-сид — с пустым
  «автоматическим» реквизитом; `create_app(v3_scope=False)`; `/_fail` для любого метода.

## [0.3.0] — 2026-10-02

### Добавлено

- Идемпотентное создание задач: тег `fl-<sha1(ключа дедупа)[:10]>` и `find(dedup_key)` —
  если ответ на `tasks.task.add` потерян (502 прокси, таймаут), ядро находит уже созданную
  задачу вместо дубля. Мок: фильтр `tasks.task.list` по `TAG`, хук `POST /_fail`
  (`after_store` — задача сохранена, ответ 502).

- Нотификатор `Bitrix24TasksNotifier` (entry point `floweon.notifiers` →
  `intelbit.notifier.bitrix24_tasks`): проблемы шины Фловеона — задачами Bitrix24 (4-17-27).
  - `notify(mode=create)` — `tasks.task.add`: `TITLE` (≤ 250), `DESCRIPTION` (BBCode
    экранирован), `RESPONSIBLE_ID`, `GROUP_ID`, `DEADLINE` (now + `deadline_hours`, ISO с
    таймзоной), `TAGS` (`floweon`, пресет), `UF_CRM_TASK` (привязка к карточке CRM),
    `PRIORITY` 2 для ошибок;
  - `notify(mode=comment)` — сообщение в чат задачи REST v3
    `tasks.task.chat.message.send` (ZWSP-экранирование); без v3 — запасной
    `task.comment.add` (форум, в интерфейсе задачи не виден) и `comments_channel=forum`
    в health;
  - `notify(mode=send)` — `im.message.add` (сводка, ≤ 4000 символов);
  - `status(task_id)` — `tasks.task.get` (`select` ЗАГЛАВНЫМИ), открыта при статусе 2/3/4/6.
- Мок Bitrix24: `tasks.task.add/get/update/list`, `task.comment.add`, `im.message.add`,
  REST v3 `/rest/api/…/tasks.task.chat.message.send`, `create_app(v3_enabled=False)`, хук
  `POST /_tasks/{id}/status`; `/_state` — `tasks`, `task_chat`, `task_forum`, `im_messages`.

### Изменено

- SDK `v0.3.1` (`NotifierPlugin.notify/status`), `intelbit-bitrix24-client` `v0.3.0`
  (`call_v3`, `bbcode`).

## [0.2.2] — 2026-10-02

### Добавлено

- TLS к порталу: `ca_bundle` (корпоративный CA), `verify_ssl`, `allow_insecure_tls` — по
  образцу коннектора SAP; `verify_ssl=false` без `allow_insecure_tls` и отсутствующий файл
  CA → `ConfigurationError`. Зависимость `intelbit-bitrix24-client` `v0.2.0` (параметры
  `verify` / `ca_bundle`). Заметка README «ожидает v0.2» снята (4-17-26).

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
