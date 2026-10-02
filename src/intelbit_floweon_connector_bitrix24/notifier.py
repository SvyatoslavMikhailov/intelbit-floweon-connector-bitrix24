"""Bitrix24TasksNotifier — проблемы шины Фловеона как задачи Bitrix24 (4-17-27).

Режимы `notify` выбирает ядро (оно ведёт дедупликацию «одна открытая задача на одну
проблему»):

- `create` — `tasks.task.add`: ответственный, группа, дедлайн, теги, привязка к
  карточке CRM (`UF_CRM_TASK`), приоритет для ошибок;
- `comment` — сообщение в **чат задачи** (REST v3 `tasks.task.chat.message.send`):
  интерфейс задачи показывает чат, а не форум. Если портал не знает v3-метода —
  запасной путь `task.comment.add` (форум, в интерфейсе задачи НЕ виден) с пометкой
  `comments_channel=forum` в health, чтобы администратор об этом знал;
- `send` — `im.message.add` (сводка в чат или пользователю).

`status(external_id)` — открыта ли задача (статусы 2/3/4/6 — в работе, 5/7 — закрыта).
`find(dedup_key)` — открытая задача с тегом `fl-<sha1(ключа)[:10]>`, который ставится при
создании: если ответ на создание потерян (5xx прокси, таймаут), ядро сначала ищет задачу.
Конфиг — тот же, что у коннектора пресета (вебхук, TLS); секрета вебхуков не требуется.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from floweon_sdk import PluginManifest, PluginType
from floweon_sdk.connector import PluginHealth
from floweon_sdk.notifier import Notification, NotifierPlugin, NotifyResult
from intelbit_bitrix24_client import Bitrix24Client, Bitrix24Error, bbcode

from intelbit_floweon_connector_bitrix24.connector import _resolve_tls

_MANIFEST = PluginManifest(
    id="intelbit.notifier.bitrix24_tasks",
    version="0.3.0",
    plugin_type=PluginType.NOTIFIER,
    name="Bitrix24 Tasks Notifier",
    description="Уведомления Интелбит.Фловеон задачами и сообщениями Bitrix24",
    author="ООО Интелбит",
    license="Apache-2.0",
)

_TITLE_MAX = 250
_MESSAGE_MAX = 4000
# Статусы задач Bitrix24: 2 ждёт выполнения, 3 выполняется, 4 ждёт контроля, 6 отложена
# — открыта; 5 завершена, 7 отклонена — закрыта.
_OPEN_STATUSES = frozenset({2, 3, 4, 6})
_METHOD_NOT_FOUND = "ERROR_METHOD_NOT_FOUND"


def dedup_tag(dedup_key: str) -> str:
    """Тег задачи с хешем ключа дедупа: по нему ищется задача, если ответ на создание потерян."""
    return "fl-" + hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:10]


def _status_value(task: dict[str, Any]) -> int:
    raw = task.get("status", task.get("STATUS"))
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 0


class Bitrix24TasksNotifier(NotifierPlugin):
    """Нотификатор: задачи Bitrix24 + чат задачи + сообщения im."""

    manifest = _MANIFEST

    def __init__(
        self,
        config: dict[str, Any],
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        verify, ca_bundle = _resolve_tls(config)
        self._client = Bitrix24Client(
            str(config["webhook_base_url"]),
            rps=float(config.get("rate_limit_rps", 2.0)),
            timeout=float(config.get("timeout", 30.0)),
            verify=verify,
            ca_bundle=ca_bundle,
            _transport=_transport,
        )
        self._comments_channel = "chat"

    async def start(self) -> None:
        """Ресурсов нет: клиент открывает соединение на каждый запрос."""

    async def stop(self) -> None:
        """Соединения не держим между вызовами."""

    async def health_check(self) -> PluginHealth:
        configured = bool(self.config.get("webhook_base_url"))
        if not configured:
            return PluginHealth(healthy=False, message="webhook_base_url не задан")
        if self._comments_channel == "forum":
            # Комментарии уходят в форум задачи — человек в задаче их не видит.
            return PluginHealth(healthy=True, message="comments_channel=forum")
        return PluginHealth(healthy=True, message="")

    # ------------------------------------------------------------------ #

    async def notify(self, notification: Notification) -> NotifyResult:
        mode = notification.get("mode", "create")
        if mode == "comment":
            return await self._comment(notification)
        if mode == "send":
            return await self._send(notification)
        return await self._create(notification)

    async def status(self, external_id: str) -> dict[str, Any]:
        envelope = await self._client.call(
            "tasks.task.get", {"taskId": external_id, "select": ["ID", "STATUS"]}
        )
        result = envelope.get("result") or {}
        task = result.get("task", result) if isinstance(result, dict) else {}
        status = _status_value(task if isinstance(task, dict) else {})
        return {"open": status in _OPEN_STATUSES, "status": status}

    async def find(self, dedup_key: str) -> dict[str, Any]:
        """Открытая задача с тегом ключа (создание идемпотентно при потерянном ответе)."""
        envelope = await self._client.call(
            "tasks.task.list",
            {"filter": {"TAG": dedup_tag(dedup_key)}, "select": ["ID", "STATUS"]},
        )
        result = envelope.get("result") or {}
        tasks = result.get("tasks", []) if isinstance(result, dict) else []
        for task in tasks:
            if isinstance(task, dict) and _status_value(task) in _OPEN_STATUSES:
                return {"external_id": str(task.get("id", task.get("ID")))}
        return {"external_id": None}

    # ------------------------------------------------------------------ #

    async def _create(self, n: Notification) -> NotifyResult:
        route = n["route"]
        deadline = datetime.now(UTC) + timedelta(hours=int(route.get("deadline_hours") or 24))
        context = n.get("context") or {}
        tags = ["floweon"]
        if context.get("preset"):
            tags.append(str(context["preset"]))
        if n.get("dedup_key"):
            tags.append(dedup_tag(n["dedup_key"]))
        fields: dict[str, Any] = {
            "TITLE": n["title"][:_TITLE_MAX],
            "DESCRIPTION": bbcode.escape(n["body"]),
            "RESPONSIBLE_ID": route["responsible_id"],
            "DEADLINE": deadline.isoformat(timespec="seconds"),
            "TAGS": tags,
        }
        if route.get("group_id"):
            fields["GROUP_ID"] = route["group_id"]
        if n.get("crm_binding"):
            fields["UF_CRM_TASK"] = [n["crm_binding"]]
        if n.get("severity") == "error":
            fields["PRIORITY"] = 2
        envelope = await self._client.call("tasks.task.add", {"fields": fields})
        result = envelope.get("result") or {}
        task = result.get("task", result) if isinstance(result, dict) else {}
        task_id = task.get("id", task.get("ID")) if isinstance(task, dict) else None
        if task_id is None:
            raise Bitrix24Error("bad_response", "tasks.task.add не вернул id задачи")
        return {"action": "created", "external_id": str(task_id)}

    async def _comment(self, n: Notification) -> NotifyResult:
        external_id = str(n.get("external_id") or "")
        if not external_id:
            raise ValueError("notify(mode=comment) требует external_id задачи")
        try:
            await self._client.call_v3(
                "tasks.task.chat.message.send",
                {"fields": {"taskId": int(external_id), "text": bbcode.escape_chat(n["body"])}},
            )
            self._comments_channel = "chat"
        except Bitrix24Error as exc:
            if exc.code != _METHOD_NOT_FOUND:
                raise
            # Портал без REST v3: форум задачи (в интерфейсе не виден) — лучше, чем ничего.
            self._comments_channel = "forum"
            await self._client.call(
                "task.comment.add",
                {"taskId": external_id, "commentText": bbcode.escape(n["body"])},
            )
        return {"action": "commented", "external_id": external_id}

    async def _send(self, n: Notification) -> NotifyResult:
        await self._client.call(
            "im.message.add",
            {
                "DIALOG_ID": n["route"]["responsible_id"],
                "MESSAGE": bbcode.escape_chat(n["body"])[:_MESSAGE_MAX],
            },
        )
        return {"action": "sent"}
