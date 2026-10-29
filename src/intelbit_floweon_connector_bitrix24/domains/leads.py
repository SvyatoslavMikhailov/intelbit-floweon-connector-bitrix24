"""Домен «Лиды»: crm.lead.* + семантика стадий crm.status.list (4-17-30).

Успешность лида — по семантике стадии, а не по ID стадий (у портала свои стадии):
справочник `crm.status.list` с `ENTITY_ID = STATUS` отдаёт `SEMANTICS` (`S` — успех,
`F` — провал, пусто — в работе); на части версий семантика — в `EXTRA.SEMANTICS`
(`success` / `failure` / `apology`). Запасной путь — поле лида `STATUS_SEMANTIC_ID`.
"""

from __future__ import annotations

from typing import Any

from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24 import fieldmaps

_EXTRA_SEMANTICS = {"success": "S", "failure": "F", "apology": "F", "process": "P"}


def _semantics(row: dict[str, Any]) -> str:
    value = str(row.get("SEMANTICS") or "").upper()
    if value in ("S", "F", "P"):
        return value
    extra = row.get("EXTRA")
    if isinstance(extra, dict):
        return _EXTRA_SEMANTICS.get(str(extra.get("SEMANTICS") or "").lower(), "P")
    return "P"


class LeadsDomain:
    """Лид по ID с семантикой его стадии."""

    def __init__(self, client: Bitrix24Client) -> None:
        self._client = client

    async def stage_semantics(self) -> dict[str, str]:
        """STATUS_ID стадии лида → S / F / P."""
        params = {"filter": {"ENTITY_ID": "STATUS"}}
        rows = [row async for row in self._client.list_all("crm.status.list", params)]
        return {str(r.get("STATUS_ID")): _semantics(r) for r in rows}

    async def get(self, lead_id: int | str) -> dict[str, Any]:
        """Лид в каноническом виде + `status_semantics` (S / F / P)."""
        env = await self._client.call("crm.lead.get", {"id": lead_id})
        lead = fieldmaps.to_canonical(env.get("result", {}) or {}, fieldmaps.LEAD)
        semantics = (await self.stage_semantics()).get(str(lead.get("status_id")))
        if semantics is None:
            # Стадии нет в справочнике (удалена, иная воронка) — семантика самого лида.
            semantics = str(lead.get("status_semantic_id") or "P").upper()
        lead["status_semantics"] = semantics
        company = str(lead.get("company_id") or "")
        lead["company_id"] = "" if company in ("", "0") else company
        return lead
