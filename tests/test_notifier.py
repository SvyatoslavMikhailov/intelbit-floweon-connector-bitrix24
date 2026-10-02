"""Нотификатор Bitrix24TasksNotifier (4-17-27): задачи, чат v3, форум-fallback, im, статус."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytest
from intelbit_bitrix24_client import Bitrix24Error, bbcode

from intelbit_floweon_connector_bitrix24 import Bitrix24TasksNotifier
from tests.conftest import MOCK_BASE
from tests.mock_bitrix24 import create_app


def _notifier(transport: httpx.ASGITransport, **extra: object) -> Bitrix24TasksNotifier:
    return Bitrix24TasksNotifier(
        {"webhook_base_url": MOCK_BASE, "rate_limit_rps": 1000.0, **extra}, _transport=transport
    )


async def _state(transport: httpx.ASGITransport) -> dict[str, Any]:
    async with httpx.AsyncClient(transport=transport, base_url="http://mock-b24") as client:
        return dict((await client.get("/_state")).json())


async def _close(transport: httpx.ASGITransport, task_id: str, status: int = 5) -> None:
    async with httpx.AsyncClient(transport=transport, base_url="http://mock-b24") as client:
        await client.post(f"/_tasks/{task_id}/status", json={"status": status})


def _create(**extra: Any) -> dict[str, Any]:
    return {
        "kind": "inbox_task",
        "mode": "create",
        "dedup_key": "k1",
        "title": "Контрагент без ИНН — не выгружен в SAP",
        "body": "Компания [b]ООО Пион[/b] без ИНН.\nЗаполните реквизиты.",
        "severity": "error",
        "route": {"responsible_id": "17", "group_id": "35", "deadline_hours": 8},
        "crm_binding": "CO_3",
        "context": {"preset": "intelbit.b24-sap"},
        **extra,
    }


class TestCreate:
    async def test_task_fields(self) -> None:
        transport = httpx.ASGITransport(app=create_app())
        result = await _notifier(transport).notify(_create())  # type: ignore[arg-type]
        assert result["action"] == "created"
        (task,) = (await _state(transport))["tasks"]
        assert task["ID"] == result["external_id"]
        assert task["TITLE"] == "Контрагент без ИНН — не выгружен в SAP"
        assert task["RESPONSIBLE_ID"] == "17"
        assert task["GROUP_ID"] == "35"
        assert task["UF_CRM_TASK"] == ["CO_3"]
        assert task["TAGS"][:2] == ["floweon", "intelbit.b24-sap"]
        assert task["TAGS"][2].startswith("fl-")  # тег ключа дедупа (поиск при потере ответа)
        assert task["PRIORITY"] == "2"
        # Описание: bbcode экранирован сущностями, переносы строк сохранены.
        assert "&#91;b&#93;ООО Пион&#91;/b&#93;" in task["DESCRIPTION"]
        assert "\n" in task["DESCRIPTION"]
        deadline = datetime.fromisoformat(task["DEADLINE"])
        assert deadline.tzinfo is not None

    async def test_optional_fields_omitted(self) -> None:
        transport = httpx.ASGITransport(app=create_app())
        n = _create(severity="warning", route={"responsible_id": "17"})
        n.pop("crm_binding")
        n["context"] = {}
        await _notifier(transport).notify(n)  # type: ignore[arg-type]
        (task,) = (await _state(transport))["tasks"]
        assert "UF_CRM_TASK" not in task
        assert "GROUP_ID" not in task
        assert "PRIORITY" not in task
        assert task["TAGS"][0] == "floweon" and len(task["TAGS"]) == 2  # + тег ключа

    async def test_title_truncated(self) -> None:
        transport = httpx.ASGITransport(app=create_app())
        await _notifier(transport).notify(_create(title="x" * 400))  # type: ignore[arg-type]
        (task,) = (await _state(transport))["tasks"]
        assert len(task["TITLE"]) == 250


class TestComment:
    async def test_v3_chat_message(self) -> None:
        transport = httpx.ASGITransport(app=create_app())
        notifier = _notifier(transport)
        created = await notifier.notify(_create())  # type: ignore[arg-type]
        result = await notifier.notify(  # type: ignore[arg-type]
            {
                **_create(),
                "mode": "comment",
                "external_id": created["external_id"],
                "body": "Повторилось [b]3[/b] раза",
            }
        )
        assert result == {"action": "commented", "external_id": created["external_id"]}
        state = await _state(transport)
        assert state["task_forum"] == []
        (message,) = state["task_chat"]
        assert message["task_id"] == int(created["external_id"])
        assert message["text"] == bbcode.escape_chat("Повторилось [b]3[/b] раза")
        assert (await notifier.health_check()).message == ""

    async def test_forum_fallback_without_v3(self) -> None:
        transport = httpx.ASGITransport(app=create_app(v3_enabled=False))
        notifier = _notifier(transport)
        created = await notifier.notify(_create())  # type: ignore[arg-type]
        await notifier.notify(  # type: ignore[arg-type]
            {**_create(), "mode": "comment", "external_id": created["external_id"], "body": "x"}
        )
        state = await _state(transport)
        assert state["task_chat"] == []
        assert state["task_forum"] == [{"task_id": int(created["external_id"]), "text": "x"}]
        health = await notifier.health_check()
        assert health.healthy is True
        assert health.message == "comments_channel=forum"


class TestSendAndStatus:
    async def test_send_digest_truncated(self) -> None:
        transport = httpx.ASGITransport(app=create_app())
        result = await _notifier(transport).notify(  # type: ignore[arg-type]
            {
                **_create(),
                "kind": "digest",
                "mode": "send",
                "route": {"responsible_id": "chat12"},
                "body": "[b]Сводка[/b] " + "я" * 5000,
            }
        )
        assert result == {"action": "sent"}
        (message,) = (await _state(transport))["im_messages"]
        assert message["dialog_id"] == "chat12"
        assert len(message["message"]) == 4000
        assert message["message"].startswith(f"[{bbcode.ZWSP}b]Сводка")

    async def test_status_open_then_closed(self) -> None:
        transport = httpx.ASGITransport(app=create_app())
        notifier = _notifier(transport)
        task_id = (await notifier.notify(_create()))["external_id"]  # type: ignore[arg-type]
        assert await notifier.status(task_id) == {"open": True, "status": 2}
        await _close(transport, task_id, 5)
        assert await notifier.status(task_id) == {"open": False, "status": 5}
        await _close(transport, task_id, 6)  # отложена — всё ещё открыта
        assert (await notifier.status(task_id))["open"] is True


class TestIdempotentCreate:
    """find(dedup_key): задача ищется по тегу ключа, если ответ на создание потерян."""

    def _setup(self) -> tuple[Bitrix24TasksNotifier, httpx.ASGITransport]:
        transport = httpx.ASGITransport(app=create_app())
        return _notifier(transport), transport

    async def _fail(self, transport: httpx.ASGITransport, **body: Any) -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://mock-b24") as c:
            await c.post("/_fail", json={"method": "tasks.task.add", "times": 1, **body})

    async def test_tag_on_create_and_find_open(self) -> None:
        from intelbit_floweon_connector_bitrix24.notifier import dedup_tag

        notifier, transport = self._setup()
        result = await notifier.notify(_create(dedup_key="p:wf:title:3"))  # type: ignore[arg-type]
        (task,) = (await _state(transport))["tasks"]
        assert dedup_tag("p:wf:title:3") in task["TAGS"]
        assert await notifier.find("p:wf:title:3") == {"external_id": result["external_id"]}
        assert await notifier.find("другой ключ") == {"external_id": None}

    async def test_closed_task_not_found(self) -> None:
        notifier, transport = self._setup()
        result = await notifier.notify(_create(dedup_key="k"))  # type: ignore[arg-type]
        await _close(transport, result["external_id"])
        assert await notifier.find("k") == {"external_id": None}

    async def test_502_after_store_then_found(self) -> None:
        notifier, transport = self._setup()
        await self._fail(transport, after_store=True)
        with pytest.raises(Bitrix24Error) as exc_info:
            await notifier.notify(_create(dedup_key="lost"))  # type: ignore[arg-type]
        assert exc_info.value.status_code == 502
        assert (await notifier.find("lost"))["external_id"] is not None
        assert len((await _state(transport))["tasks"]) == 1

    async def test_502_before_store_nothing_created(self) -> None:
        notifier, transport = self._setup()
        await self._fail(transport)
        with pytest.raises(Bitrix24Error):
            await notifier.notify(_create(dedup_key="never"))  # type: ignore[arg-type]
        assert await notifier.find("never") == {"external_id": None}
        assert (await _state(transport))["tasks"] == []
