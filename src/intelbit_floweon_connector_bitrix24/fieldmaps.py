"""Карты стандартных полей Bitrix24 ↔ канонические ключи Фловеона.

Только **стандартные** поля (без `UF_*` и бизнес-маппингов — это пресеты/БОВА).
Ключ карты — канонический snake_case, значение — имя поля в Bitrix24.
Неизвестные ключи проходят насквозь (passthrough), чтобы пресет мог дослать своё.
"""

from __future__ import annotations

from typing import Any

# --- CRM: контрагенты (crm.company.*) -------------------------------------- #
COMPANY: dict[str, str] = {
    "id": "ID",
    "title": "TITLE",
    "company_type": "COMPANY_TYPE",
    "industry": "INDUSTRY",
    "revenue": "REVENUE",
    "currency_id": "CURRENCY_ID",
    "address": "ADDRESS",
    "address_city": "ADDRESS_CITY",
    "address_postal_code": "ADDRESS_POSTAL_CODE",
    "address_country": "ADDRESS_COUNTRY",
    "phone": "PHONE",
    "email": "EMAIL",
    "web": "WEB",
    "assigned_by_id": "ASSIGNED_BY_ID",
    "opened": "OPENED",
    "comments": "COMMENTS",
    "date_create": "DATE_CREATE",
    "date_modify": "DATE_MODIFY",
}

# --- CRM: реквизиты (crm.requisite.*) -------------------------------------- #
# Поля пресета реквизитов; ИНН/КПП нужны пресету b24-sap для дедупа контрагентов.
REQUISITE: dict[str, str] = {
    "id": "ID",
    "company_id": "ENTITY_ID",
    "preset_id": "PRESET_ID",
    "name": "NAME",
    "inn": "RQ_INN",
    "kpp": "RQ_KPP",
    "ogrn": "RQ_OGRN",
    "company_name": "RQ_COMPANY_NAME",
}

# --- Торговый каталог: товары (catalog.product.*) — новый camelCase-API ----- #
PRODUCT: dict[str, str] = {
    "id": "id",
    "iblock_id": "iblockId",
    "name": "name",
    "code": "code",
    "active": "active",
    "measure": "measure",
    "iblock_section_id": "iblockSectionId",
    "detail_text": "detailText",
    "preview_text": "previewText",
}

# --- Торговый каталог: цены (catalog.price.*) ------------------------------- #
PRICE: dict[str, str] = {
    "id": "id",
    "product_id": "productId",
    "catalog_group_id": "catalogGroupId",
    "price": "price",
    "currency": "currency",
}

# --- Склады (catalog.store.*) ---------------------------------------------- #
STORE: dict[str, str] = {
    "id": "id",
    "title": "title",
    "active": "active",
    "address": "address",
}

# --- Остатки на складе (catalog.storeproduct.*) ---------------------------- #
STORE_PRODUCT: dict[str, str] = {
    "id": "id",
    "store_id": "storeId",
    "product_id": "productId",
    "amount": "amount",
    "quantity_reserved": "quantityReserved",
}

# --- CRM: сделки (crm.deal.*) ---------------------------------------------- #
DEAL: dict[str, str] = {
    "id": "ID",
    "title": "TITLE",
    "category_id": "CATEGORY_ID",
    "stage_id": "STAGE_ID",
    "company_id": "COMPANY_ID",
    "contact_id": "CONTACT_ID",
    "opportunity": "OPPORTUNITY",
    "currency_id": "CURRENCY_ID",
    "assigned_by_id": "ASSIGNED_BY_ID",
    "begindate": "BEGINDATE",
    "closedate": "CLOSEDATE",
    "closed": "CLOSED",
    "opened": "OPENED",
    "comments": "COMMENTS",
    "date_create": "DATE_CREATE",
    "date_modify": "DATE_MODIFY",
}

# --- CRM: товарные строки сделки (crm.deal.productrows.*) ------------------- #
DEAL_PRODUCTROW: dict[str, str] = {
    "product_id": "PRODUCT_ID",
    "product_name": "PRODUCT_NAME",
    "price": "PRICE",
    "quantity": "QUANTITY",
    "measure_code": "MEASURE_CODE",
}


def to_canonical(raw: dict[str, Any], fmap: dict[str, str]) -> dict[str, Any]:
    """Сырая запись Bitrix24 → канонический dict (неизвестные поля — насквозь)."""
    inverse = {b24: canon for canon, b24 in fmap.items()}
    return {inverse.get(key, key): value for key, value in raw.items()}


def to_bitrix(canon: dict[str, Any], fmap: dict[str, str]) -> dict[str, Any]:
    """Канонический dict → поля Bitrix24 (неизвестные ключи — насквозь)."""
    return {fmap.get(key, key): value for key, value in canon.items()}
