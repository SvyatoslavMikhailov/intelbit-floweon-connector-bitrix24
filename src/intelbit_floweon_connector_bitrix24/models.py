"""Pydantic-модели стандартных сущностей Bitrix24 (канонический вид).

Все поля опциональны, кроме `id`, где он естественен: коннектор отдаёт ровно те
поля, что вернул Bitrix24 (стандартный набор), а пресет дополняет своими.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Canon(BaseModel):
    # Разрешаем нестандартные поля (пресет может дослать своё), без отбрасывания.
    model_config = ConfigDict(extra="allow")


class Company(_Canon):
    id: int | str | None = None
    title: str | None = None
    company_type: str | None = None
    industry: str | None = None
    currency_id: str | None = None
    assigned_by_id: int | str | None = None


class Requisite(_Canon):
    id: int | str | None = None
    company_id: int | str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    company_name: str | None = None


class Product(_Canon):
    id: int | None = None
    iblock_id: int | None = None
    name: str | None = None
    code: str | None = None
    active: str | None = None
    measure: int | None = None


class Price(_Canon):
    id: int | None = None
    product_id: int | None = None
    catalog_group_id: int | None = None
    price: float | str | None = None
    currency: str | None = None


class Store(_Canon):
    id: int | None = None
    title: str | None = None
    active: str | None = None
    address: str | None = None


class StoreProduct(_Canon):
    id: int | None = None
    store_id: int | None = None
    product_id: int | None = None
    amount: float | str | None = None
    quantity_reserved: float | str | None = None


class Deal(_Canon):
    id: int | str | None = None
    title: str | None = None
    category_id: int | str | None = None
    stage_id: str | None = None
    company_id: int | str | None = None
    opportunity: float | str | None = None
    currency_id: str | None = None


class DealProductRow(_Canon):
    product_id: int | str | None = None
    product_name: str | None = None
    price: float | str | None = None
    quantity: float | str | None = None
    measure_code: int | str | None = None
