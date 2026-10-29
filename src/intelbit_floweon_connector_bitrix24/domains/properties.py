"""Товары по свойству инфоблока: пакетные операции сопоставления (4-17-30).

Ключ товара — значение свойства (`propertyNN` в API `catalog.product.*`), а не
`code`/`XML_ID`. Пресет называет свойства псевдонимами (`ref`, `current_material`),
коды задаёт конфиг коннектора `product_properties` (`PROPERTY_61`, `property61`, `61`).

Запись свойства — объект `{value, valueId}`: строку коробка молча превращает в пустое
значение и отвечает 200. Поэтому после записи значение всегда читается обратно.
"""

from __future__ import annotations

import re
from typing import Any

from intelbit_floweon_connector_bitrix24.domains.catalog import CatalogDomain
from intelbit_floweon_connector_bitrix24.domains.stock import StockDomain

PROPERTY_WRITE_LOST = "property_write_lost"
_CODE = re.compile(r"^(?:property_?)?(\d+)$", re.IGNORECASE)


def property_field(code: str) -> str:
    """`PROPERTY_61` / `property61` / `61` → поле API `property61`."""
    match = _CODE.match(str(code).strip())
    if match is None:
        raise ValueError(f"код свойства товара {code!r}: ожидается PROPERTY_<ID>")
    return f"property{match.group(1)}"


def property_value(raw: Any) -> str:
    """Значение свойства из ответа: `{value, valueId}`, список таких или скаляр."""
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, dict):
        raw = raw.get("value")
    return "" if raw is None else str(raw).strip()


def _value_id(raw: Any) -> Any:
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return raw.get("valueId") if isinstance(raw, dict) else None


class ProductProperties:
    """Операции над товарами каталога, найденными по значению свойства."""

    def __init__(self, catalog: CatalogDomain, stock: StockDomain, aliases: dict[str, str]) -> None:
        self._catalog = catalog
        self._stock = stock
        self._aliases = {k: v for k, v in aliases.items() if str(v or "").strip()}

    def field(self, alias: str) -> str:
        """Псевдоним пресета → поле API; незаданный код — понятная ошибка конфига."""
        if alias not in self._aliases:
            raise ValueError(
                f"свойство товара {alias!r} не задано в конфиге коннектора (product_properties)"
            )
        return property_field(self._aliases[alias])

    async def _products(
        self, fields: list[str], filter_: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return await self._catalog.list_records(filter_, ["id", "iblockId", "name", *fields])

    async def _write(self, product_id: int, field: str, value: str, raw_old: Any) -> None:
        """Записать свойство объектом и проверить чтением (иначе — PROPERTY_WRITE_LOST)."""
        payload: dict[str, Any] = {"value": value}
        value_id = _value_id(raw_old)
        if value_id is not None:
            payload["valueId"] = value_id
        await self._catalog.update(product_id, {field: payload})
        await self._verify(product_id, field, value)

    async def _verify(self, product_id: int, field: str, value: str) -> None:
        rows = await self._products([field], {"id": product_id})
        stored = property_value(rows[0].get(field)) if rows else ""
        if stored != value:
            raise ValueError(
                f"{PROPERTY_WRITE_LOST}: товар {product_id}, {field}: записано {value!r}, "
                f"прочитано {stored!r}"
            )

    async def sync(
        self,
        key_property: str,
        value_property: str,
        items: list[dict[str, Any]],
        key_field: str,
        value_field: str,
        sample_size: int = 20,
    ) -> dict[str, Any]:
        """Свойство value у товаров по ключевому свойству — только изменившиеся.

        Returns:
            changed — [{key, product_id, old, new}]; unchanged — число; without_value —
            товары с ключом, для которого во входе нет значения; missing — ключи входа без
            товара ({count, sample}).
        """
        kf, vf = self.field(key_property), self.field(value_property)
        wanted: dict[str, str] = {}
        for item in items:
            key = str(item.get(key_field) or "").strip()
            if key:
                wanted[key] = str(item.get(value_field) or "").strip()
        changed: list[dict[str, Any]] = []
        without_value: list[str] = []
        seen: set[str] = set()
        unchanged = 0
        for product in await self._products([kf, vf]):
            key = property_value(product.get(kf))
            if not key:
                continue  # товар без ключа (не из SAP) — не наш
            seen.add(key)
            new = wanted.get(key, "")
            if not new:
                without_value.append(f"{key} — товар {product['id']} «{product.get('name', '')}»")
                continue
            old = property_value(product.get(vf))
            if old == new:
                unchanged += 1
                continue
            await self._write(int(product["id"]), vf, new, product.get(vf))
            changed.append({"key": key, "product_id": int(product["id"]), "old": old, "new": new})
        missing = sorted(k for k in wanted if k not in seen)
        return {
            "changed": changed,
            "unchanged": unchanged,
            "without_value": without_value,
            "missing": {"count": len(missing), "sample": missing[:sample_size]},
        }

    async def sync_stock(
        self,
        key_property: str,
        items: list[dict[str, Any]],
        store_id: int,
        scope_property: str | None = None,
    ) -> dict[str, Any]:
        """Остаток товарам по ключевому свойству (`code` входа = значение свойства).

        Ключ входа без товара — не ошибка (нетекущий материал того же REF). Товар с
        `scope_property`, но без ключевого свойства — в without_key (одна задача).
        """
        kf = self.field(key_property)
        sf = self.field(scope_property) if scope_property else None
        amounts = {
            str(i.get("code") or "").strip(): i.get("amount")
            for i in items
            if str(i.get("code") or "").strip()
        }
        written = 0
        without_key: list[str] = []
        for product in await self._products([kf, *([sf] if sf else [])]):
            key = property_value(product.get(kf))
            if not key:
                if sf and property_value(product.get(sf)):
                    without_key.append(
                        f"{property_value(product.get(sf))} — товар {product['id']} "
                        f"«{product.get('name', '')}»"
                    )
                continue
            amount = amounts.get(key)
            if amount is None or amount == "":
                continue  # по материалу нет строк остатка в SAP — товар не трогаем
            await self._stock.set_amount(
                store_id, int(product["id"]), float(amount), title=f"Фловеон: остаток {key}"
            )
            written += 1
        return {"written": written, "without_key": without_key}

    async def upsert(
        self,
        key_property: str,
        key: str,
        name: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Товар по ключевому свойству: есть — обновить только свойства, нет — создать."""
        kf = self.field(key_property)
        fields = {self.field(alias): str(v or "").strip() for alias, v in properties.items()}
        key = str(key or "").strip()
        if not key:
            raise ValueError("upsert по свойству: пустой ключ")
        # Фильтр по свойству коробка может проигнорировать — совпадение перепроверяется.
        rows = await self._products([kf, *fields], {kf: key})
        found = [r for r in rows if property_value(r.get(kf)) == key]
        if found:
            product = found[0]
            updated = []
            for field, value in fields.items():
                if property_value(product.get(field)) != value:
                    await self._write(int(product["id"]), field, value, product.get(field))
                    updated.append(field)
            return {"id": int(product["id"]), "op": "update" if updated else "unchanged"}
        if not str(name or "").strip():
            raise ValueError(f"создание товара по ключу {key!r}: нет наименования")
        product_id = await self._catalog.add(
            {"name": name, kf: {"value": key}, **{f: {"value": v} for f, v in fields.items()}}
        )
        for field, value in {kf: key, **fields}.items():
            await self._verify(product_id, field, value)
        return {"id": product_id, "op": "add"}
