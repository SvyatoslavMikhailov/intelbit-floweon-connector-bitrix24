# CLAUDE.md — intelbit-floweon-connector-bitrix24

Гайд для Claude Code по этому репозиторию.

## Что это

Коннектор Bitrix24-коробки для Интелбит.Фловеон. Ядро со **стандартными полями** четырёх
доменов (контрагенты, материалы+цены, остатки, сделки). Построен на общем Apache-клиенте
`intelbit-bitrix24-client` и контракте `ConnectorPlugin` из `floweon-sdk`.

## Документация

Проектная документация — Obsidian, папка `4 Мои проекты/4-17 Интелбит Фловеон/`;
промпты — `04 Промпты для Claude Code/`, статус — `04 Промпты для Claude Code/Статус разработки.md`.

## Архитектура

- `connector.py` — `Bitrix24Connector(ConnectorPlugin)`: lifecycle (init/start/stop/
  health_check/reload из SDK) + `read`/`write`/`subscribe`. Композиция четырёх доменов.
- `domains/` — адаптеры доменов поверх `Bitrix24Client`: `companies` (company+requisite),
  `catalog` (product+price), `stock` (store+store_product), `deals` (deal+productrows).
- `fieldmaps.py` — карты стандартных полей B24 ↔ канонические ключи. Неизвестные поля —
  насквозь (пресет дополняет своё).
- `models.py` — Pydantic-модели стандартных сущностей (extra="allow").
- `webhooks.py` — приём исходящих вебхуков коробки → канонический Event с idempotency-key.
- `manifest/connector-manifest.yaml`, `config_schema.json` — описание плагина и конфига.

## Контракт ADR-006

- Методы idempotent относительно retry.
- Соединения **не держим** между вызовами: клиент открывает/закрывает `httpx.AsyncClient`
  на каждый запрос; in-memory state между вызовами нет.
- Payload — JSON-serializable.

## Границы (вне scope ядра)

- Пользовательские поля `UF_*` и бизнес-маппинги направлений — это пресеты (`b24-sap`,
  `crm-onec`) и БОВА-расширение, отдельные репозитории/промпты.
- OAuth/Marketplace-авторизация — v1.1 (ядро под входящий вебхук коробки).
- Псевдо-события для каталога/остатков — не делаем (у коробки их нет → pull).

## Команды

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy
uv run pytest          # -m contract для contract-тестов
```

## Зависимости (git-теги в `[tool.uv.sources]`)

- `intelbit-bitrix24-client` (тег `v0.1.0`) — REST-клиент Bitrix24.
- `intelbit-floweon-sdk` (тег `v0.2.0`) — `floweon_sdk` (`ConnectorPlugin`, manifest).

---

## LLM Coding Guidelines (Karpathy)

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

*Source: https://github.com/forrestchang/andrej-karpathy-skills/blob/main/CLAUDE.md*
