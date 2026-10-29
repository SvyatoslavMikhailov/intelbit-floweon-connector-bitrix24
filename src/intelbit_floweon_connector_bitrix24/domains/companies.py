"""Домен «Контрагенты»: crm.company.* + реквизиты crm.requisite.* (ИНН/КПП)."""

from __future__ import annotations

from typing import Any

from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24 import fieldmaps

# ENTITY_TYPE_ID компании в CRM (реквизиты бывают и у контактов — 3).
_COMPANY_TYPE_ID = "4"


class CompaniesDomain:
    """Контрагенты Bitrix24 со стандартными полями + реквизиты для дедупа по ИНН/КПП."""

    def __init__(self, client: Bitrix24Client) -> None:
        self._client = client

    # --- компании --------------------------------------------------------- #

    async def list_records(
        self,
        filter: dict[str, Any] | None = None,
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = fieldmaps.to_bitrix(filter, fieldmaps.COMPANY)
        params["select"] = select or list(fieldmaps.COMPANY.values())
        rows = [row async for row in self._client.list_all("crm.company.list", params)]
        return [fieldmaps.to_canonical(r, fieldmaps.COMPANY) for r in rows]

    async def get(self, company_id: int | str) -> dict[str, Any]:
        env = await self._client.call("crm.company.get", {"id": company_id})
        return fieldmaps.to_canonical(env.get("result", {}) or {}, fieldmaps.COMPANY)

    async def add(self, data: dict[str, Any]) -> int:
        fields = fieldmaps.to_bitrix(data, fieldmaps.COMPANY)
        env = await self._client.call("crm.company.add", {"fields": fields})
        return int(env["result"])

    async def update(self, company_id: int | str, data: dict[str, Any]) -> bool:
        fields = fieldmaps.to_bitrix(data, fieldmaps.COMPANY)
        env = await self._client.call("crm.company.update", {"id": company_id, "fields": fields})
        return bool(env.get("result"))

    async def delete(self, company_id: int | str) -> bool:
        env = await self._client.call("crm.company.delete", {"id": company_id})
        return bool(env.get("result"))

    # --- реквизиты (ИНН/КПП/ОГРН) ----------------------------------------- #

    async def list_requisites(self, company_id: int | str) -> list[dict[str, Any]]:
        """Реквизиты контрагента: канонические dict с inn/kpp/ogrn, реквизиты с ИНН — первыми.

        Коробка при создании компании сама заводит пустой реквизит (ИНН null), поэтому
        первым по ID часто оказывается он, а заполненный — вторым (стенд 4-17-28).
        """
        params = {
            "filter": {"ENTITY_TYPE_ID": 4, "ENTITY_ID": company_id},
            "select": list(fieldmaps.REQUISITE.values()),
        }
        rows = [row async for row in self._client.list_all("crm.requisite.list", params)]
        canon = [fieldmaps.to_canonical(r, fieldmaps.REQUISITE) for r in rows]
        return sorted(canon, key=lambda r: not r.get("inn"))

    async def get_inn_kpp(self, company_id: int | str) -> dict[str, str | None]:
        """Удобный доступ к ИНН/КПП первого реквизита (нужно пресету b24-sap)."""
        requisites = await self.list_requisites(company_id)
        if not requisites:
            return {"inn": None, "kpp": None}
        first = requisites[0]
        return {"inn": first.get("inn"), "kpp": first.get("kpp")}

    async def add_requisite(self, data: dict[str, Any]) -> int:
        fields = fieldmaps.to_bitrix(data, fieldmaps.REQUISITE)
        env = await self._client.call("crm.requisite.add", {"fields": fields})
        return int(env["result"])

    async def update_requisite(self, requisite_id: int | str, data: dict[str, Any]) -> bool:
        fields = fieldmaps.to_bitrix(data, fieldmaps.REQUISITE)
        env = await self._client.call(
            "crm.requisite.update", {"id": requisite_id, "fields": fields}
        )
        return bool(env.get("result"))

    # --- банковские реквизиты и владелец реквизита (4-17-30) --------------- #

    async def requisite_company_id(self, requisite_id: int | str) -> str:
        """ID компании реквизита; реквизит контакта/удалённый → пусто."""
        env = await self._client.call("crm.requisite.get", {"id": requisite_id})
        raw = env.get("result") or {}
        if str(raw.get("ENTITY_TYPE_ID")) != _COMPANY_TYPE_ID:
            return ""
        return str(raw.get("ENTITY_ID") or "")

    async def bank_detail_company_id(self, bank_detail_id: int | str) -> str:
        """ID компании банковского реквизита (банковский реквизит → реквизит → компания)."""
        env = await self._client.call("crm.requisite.bankdetail.get", {"id": bank_detail_id})
        requisite_id = (env.get("result") or {}).get("ENTITY_ID")
        return await self.requisite_company_id(requisite_id) if requisite_id else ""

    async def list_bank_details(self, company_id: int | str) -> list[dict[str, Any]]:
        """Банковские реквизиты реквизита компании с ИНН (по ID: первый — основной).

        Берётся тот же реквизит, что и для ИНН/КПП (`list_requisites` — с ИНН первым);
        счета без номера не передаются.
        """
        requisites = await self.list_requisites(company_id)
        if not requisites or not requisites[0].get("id"):
            return []
        params = {
            "filter": {"ENTITY_ID": requisites[0]["id"]},
            "order": {"ID": "ASC"},
            "select": list(fieldmaps.BANK_DETAIL.values()),
        }
        rows = [row async for row in self._client.list_all("crm.requisite.bankdetail.list", params)]
        canon = [fieldmaps.to_canonical(r, fieldmaps.BANK_DETAIL) for r in rows]
        return [b for b in canon if str(b.get("account") or "").strip()]
