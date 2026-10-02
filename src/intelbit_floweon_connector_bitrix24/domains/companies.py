"""Домен «Контрагенты»: crm.company.* + реквизиты crm.requisite.* (ИНН/КПП)."""

from __future__ import annotations

from typing import Any

from intelbit_bitrix24_client import Bitrix24Client

from intelbit_floweon_connector_bitrix24 import fieldmaps


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
        """Реквизиты контрагента. Возвращает канонические dict с inn/kpp/ogrn."""
        params = {
            "filter": {"ENTITY_TYPE_ID": 4, "ENTITY_ID": company_id},
            "select": list(fieldmaps.REQUISITE.values()),
        }
        rows = [row async for row in self._client.list_all("crm.requisite.list", params)]
        return [fieldmaps.to_canonical(r, fieldmaps.REQUISITE) for r in rows]

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
