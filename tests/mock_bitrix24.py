"""FastAPI-мок REST Bitrix24 для contract-тестов.

Обрабатывает POST `/rest/<user>/<token>/<method>` (form-encoded), имитирует 4 домена,
батч, пагинацию (`start/next/total`), конверт ошибки и `QUERY_LIMIT_EXCEEDED`.

create_app() возвращает СВЕЖЕЕ приложение с переинициализированным хранилищем —
каждый тест берёт изолированный экземпляр.

Страница пагинации намеренно мала (MOCK_PAGE=2), чтобы дёшево гонять многостраничность.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MOCK_PAGE = 2


def _unflatten(pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """PHP-style form-пары → вложенный dict. Числовые сегменты остаются строковыми ключами."""
    root: dict[str, Any] = {}
    for raw_key, value in pairs:
        head, _, rest = raw_key.partition("[")
        keys = [head]
        if rest:
            keys += [seg.rstrip("]") for seg in rest.split("[")]
        node = root
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
    return root


def _rows(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """{"0": {...}, "1": {...}} → [ {...}, {...} ] (для rows/списков из form)."""
    return [mapping[k] for k in sorted(mapping, key=lambda x: int(x))]


def _paginate(items: list[dict[str, Any]], start: int) -> tuple[list[dict[str, Any]], int | None]:
    page = items[start : start + MOCK_PAGE]
    nxt = start + MOCK_PAGE if start + MOCK_PAGE < len(items) else None
    return page, nxt


def _seed() -> dict[str, Any]:
    return {
        "companies": {
            1: {"ID": "1", "TITLE": "ООО Ромашка", "CURRENCY_ID": "RUB"},
            2: {"ID": "2", "TITLE": "ООО Лютик", "CURRENCY_ID": "RUB"},
            3: {"ID": "3", "TITLE": "ЗАО Пион", "CURRENCY_ID": "RUB"},
        },
        "requisites": [
            {
                "ID": "11",
                "ENTITY_ID": "1",
                "ENTITY_TYPE_ID": "4",
                "RQ_INN": "7701234567",
                "RQ_KPP": "770101001",
                "RQ_OGRN": "1027700000001",
                "RQ_COMPANY_NAME": "ООО Ромашка",
            }
        ],
        "products": {
            101: {"id": 101, "iblockId": 14, "name": "Болт М6", "measure": 5},
            102: {"id": 102, "iblockId": 14, "name": "Гайка М6", "measure": 5},
            103: {"id": 103, "iblockId": 14, "name": "Шайба 6", "measure": 5},
        },
        "prices": {
            1001: {
                "id": 1001,
                "productId": 101,
                "catalogGroupId": 1,
                "price": 12.5,
                "currency": "RUB",
            },
        },
        "stores": {
            201: {"id": 201, "title": "Главный склад", "active": "Y", "address": "Москва"},
        },
        "storeproducts": {
            5001: {
                "id": 5001,
                "storeId": 201,
                "productId": 101,
                "amount": 100,
                "quantityReserved": 5,
            },
        },
        "deals": {
            301: {"ID": "301", "TITLE": "Поставка №1", "STAGE_ID": "NEW", "OPPORTUNITY": "1000"},
            302: {"ID": "302", "TITLE": "Поставка №2", "STAGE_ID": "NEW", "OPPORTUNITY": "2000"},
            303: {"ID": "303", "TITLE": "Поставка №3", "STAGE_ID": "WON", "OPPORTUNITY": "3000"},
        },
        "deal_rows": {
            301: [
                {
                    "PRODUCT_ID": "101",
                    "PRODUCT_NAME": "Болт М6",
                    "PRICE": "12.5",
                    "QUANTITY": "10",
                    "MEASURE_CODE": "796",
                }
            ],
        },
    }


def create_app(limit_methods: frozenset[str] = frozenset()) -> FastAPI:
    app = FastAPI(title="Bitrix24 Mock", version="0.1.0")
    db = _seed()
    limit_seen: dict[str, int] = {}

    def _next_id(store: dict[int, Any]) -> int:
        return (max(store) if store else 0) + 1

    def _dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
        fields = params.get("fields", {}) or {}
        start = int(params.get("start", 0) or 0)

        # --- контрагенты ---------------------------------------------------- #
        if method == "crm.company.list":
            items = list(db["companies"].values())
            page, nxt = _paginate(items, start)
            return _envelope(page, len(items), nxt)
        if method == "crm.company.get":
            return {"result": db["companies"].get(int(params["id"]), {})}
        if method == "crm.company.add":
            new_id = _next_id(db["companies"])
            db["companies"][new_id] = {"ID": str(new_id), **fields}
            return {"result": new_id}
        if method == "crm.company.update":
            db["companies"][int(params["id"])].update(fields)
            return {"result": True}
        if method == "crm.company.delete":
            db["companies"].pop(int(params["id"]), None)
            return {"result": True}

        # --- реквизиты ------------------------------------------------------ #
        if method == "crm.requisite.list":
            entity_id = str(params.get("filter", {}).get("ENTITY_ID", ""))
            items = [r for r in db["requisites"] if not entity_id or r["ENTITY_ID"] == entity_id]
            page, nxt = _paginate(items, start)
            return _envelope(page, len(items), nxt)
        if method == "crm.requisite.add":
            new_id = len(db["requisites"]) + 100
            db["requisites"].append({"ID": str(new_id), **fields})
            return {"result": new_id}
        if method == "crm.requisite.update":
            return {"result": True}

        # --- каталог: товары ------------------------------------------------ #
        if method == "catalog.product.list":
            items = list(db["products"].values())
            page, nxt = _paginate(items, start)
            return _wrapped({"products": page}, len(items), nxt)
        if method == "catalog.product.get":
            return {"result": {"product": db["products"].get(int(params["id"]), {})}}
        if method == "catalog.product.add":
            new_id = _next_id(db["products"])
            element = {"id": new_id, **fields}
            db["products"][new_id] = element
            return {"result": {"element": element}}
        if method == "catalog.product.update":
            db["products"][int(params["id"])].update(fields)
            return {"result": {"element": db["products"][int(params["id"])]}}

        # --- каталог: цены -------------------------------------------------- #
        if method == "catalog.price.list":
            items = list(db["prices"].values())
            page, nxt = _paginate(items, start)
            return _wrapped({"prices": page}, len(items), nxt)
        if method == "catalog.price.add":
            new_id = _next_id(db["prices"])
            element = {"id": new_id, **fields}
            db["prices"][new_id] = element
            return {"result": {"element": element}}
        if method == "catalog.price.update":
            db["prices"][int(params["id"])].update(fields)
            return {"result": {"element": db["prices"][int(params["id"])]}}
        if method == "catalog.priceType.list":
            return _wrapped({"priceTypes": [{"id": 1, "name": "BASE"}]}, 1, None)

        # --- склады и остатки ---------------------------------------------- #
        if method == "catalog.store.list":
            items = list(db["stores"].values())
            page, nxt = _paginate(items, start)
            return _wrapped({"stores": page}, len(items), nxt)
        if method == "catalog.store.get":
            return {"result": {"store": db["stores"].get(int(params["id"]), {})}}
        if method == "catalog.storeproduct.list":
            items = list(db["storeproducts"].values())
            page, nxt = _paginate(items, start)
            return _wrapped({"storeProducts": page}, len(items), nxt)
        if method == "catalog.storeproduct.get":
            return {"result": {"storeProduct": db["storeproducts"].get(int(params["id"]), {})}}
        if method == "catalog.storeproduct.add":
            new_id = _next_id(db["storeproducts"])
            element = {"id": new_id, **fields}
            db["storeproducts"][new_id] = element
            return {"result": {"element": element}}
        if method == "catalog.storeproduct.update":
            db["storeproducts"][int(params["id"])].update(fields)
            return {"result": {"element": db["storeproducts"][int(params["id"])]}}

        # --- сделки --------------------------------------------------------- #
        if method == "crm.deal.list":
            items = list(db["deals"].values())
            page, nxt = _paginate(items, start)
            return _envelope(page, len(items), nxt)
        if method == "crm.deal.get":
            return {"result": db["deals"].get(int(params["id"]), {})}
        if method == "crm.deal.add":
            new_id = _next_id(db["deals"])
            db["deals"][new_id] = {"ID": str(new_id), **fields}
            return {"result": new_id}
        if method == "crm.deal.update":
            db["deals"][int(params["id"])].update(fields)
            return {"result": True}
        if method == "crm.deal.delete":
            db["deals"].pop(int(params["id"]), None)
            return {"result": True}
        if method == "crm.deal.productrows.get":
            return {"result": db["deal_rows"].get(int(params["id"]), [])}
        if method == "crm.deal.productrows.set":
            rows = params.get("rows", {})
            db["deal_rows"][int(params["id"])] = _rows(rows) if isinstance(rows, dict) else rows
            return {"result": True}

        raise _MethodError(method)

    @app.post("/rest/{user_id}/{token}/{method}")
    async def handle(user_id: str, token: str, method: str, request: Request) -> JSONResponse:
        params = _unflatten((await request.form()).multi_items())

        # Симуляция QUERY_LIMIT_EXCEEDED: первый вызов помеченного метода — ошибка лимита.
        if method in limit_methods:
            seen = limit_seen.get(method, 0)
            limit_seen[method] = seen + 1
            if seen == 0:
                return JSONResponse(
                    status_code=200,
                    content={
                        "error": "QUERY_LIMIT_EXCEEDED",
                        "error_description": "Too many requests",
                    },
                )

        if method == "batch":
            return JSONResponse(_run_batch(params, _dispatch))

        try:
            return JSONResponse(_dispatch(method, params))
        except _MethodError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": "ERROR_METHOD_NOT_FOUND", "error_description": str(exc)},
            )

    return app


class _MethodError(RuntimeError):
    pass


def _envelope(rows: list[dict[str, Any]], total: int, nxt: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {"result": rows, "total": total}
    if nxt is not None:
        out["next"] = nxt
    return out


def _wrapped(result: dict[str, Any], total: int, nxt: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {"result": result, "total": total}
    if nxt is not None:
        out["next"] = nxt
    return out


def _run_batch(
    params: dict[str, Any],
    dispatch: Any,
) -> dict[str, Any]:
    cmd = params.get("cmd", {})
    result: dict[str, Any] = {}
    result_error: dict[str, Any] = {}
    result_total: dict[str, Any] = {}
    result_next: dict[str, Any] = {}
    for name, raw in cmd.items():
        method, _, query = str(raw).partition("?")
        sub_params = _unflatten(parse_qsl(query))
        try:
            env = dispatch(method, sub_params)
        except _MethodError as exc:
            result_error[name] = str(exc)
            continue
        result[name] = env.get("result")
        if "total" in env:
            result_total[name] = env["total"]
        if "next" in env:
            result_next[name] = env["next"]
    return {
        "result": {
            "result": result,
            "result_error": result_error,
            "result_total": result_total,
            "result_next": result_next,
        }
    }
