"""FastAPI-мок REST Bitrix24 для contract-тестов.

Обрабатывает POST `/rest/<user>/<token>/<method>` (form-encoded), имитирует 4 домена,
батч, пагинацию (`start/next/total`), конверт ошибки и `QUERY_LIMIT_EXCEEDED`.

create_app() возвращает СВЕЖЕЕ приложение с переинициализированным хранилищем —
каждый тест берёт изолированный экземпляр.

Страница пагинации намеренно мала (MOCK_PAGE=2), чтобы дёшево гонять многостраничность.

Задачи (нотификатор 4-17-27): `tasks.task.add/get/update/list`, форум `task.comment.add`,
`im.message.add` (v2, form) и чат задачи REST v3 — POST JSON
`/rest/api/<user>/<token>/tasks.task.chat.message.send`. `create_app(v3_enabled=False)` —
портал без v3 (ERROR_METHOD_NOT_FOUND). Хук `POST /_tasks/{id}/status` {"status": 5} —
закрыть задачу из теста. `/_state`: tasks, task_chat, task_forum, im_messages.

Приведён к коробке «Корпоративный портал» 26.x (стенд 4-17-28):
- `catalog.product.list` без `id`/`iblockId` в `select` — ошибка «Required select fields»;
- `catalog.price.add/update` отвечают под ключом `price`, а не `element`;
- `catalog.storeproduct.add/update` нет (только list/get); остатки при складском учёте
  (`create_app(inventory_mode=True)`, по умолчанию) — документами `catalog.document.*`:
  `S` (оприходование, storeTo) / `D` (списание, storeFrom), остаток меняет `conduct`;
  без учёта — `quantity` товара в `catalog.product.update`;
- `create_app(v3_scope=False)` — вебхук без scope `tasks`: v3-чат задачи отвечает
  `BITRIX_REST_V3_EXCEPTION_INSUFFICIENTSCOPEEXCEPTION`.
`/_state` дополнительно: documents.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

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


def _seed_extended() -> dict[str, Any]:
    """Сид e2e пресета b24-sap: компании с адресами и реквизитами, пустой каталог."""
    db = _seed()

    def company(cid: int, title: str, city: str, postal: str, street: str) -> dict[str, Any]:
        return {
            "ID": str(cid),
            "TITLE": title,
            "CURRENCY_ID": "RUB",
            "ADDRESS": street,
            "ADDRESS_CITY": city,
            "ADDRESS_POSTAL_CODE": postal,
            "ADDRESS_COUNTRY": "RU",
        }

    def requisite(rid: int, cid: int, inn: str, kpp: str, name: str) -> dict[str, Any]:
        return {
            "ID": str(rid),
            "ENTITY_ID": str(cid),
            "ENTITY_TYPE_ID": "4",
            "RQ_INN": inn,
            "RQ_KPP": kpp,
            "RQ_COMPANY_NAME": name,
        }

    db["companies"] = {
        1: company(1, "ООО Ромашка", "Москва", "101000", "ул. Тверская, 1"),
        2: company(2, "ООО Лютик", "Санкт-Петербург", "190000", "Невский пр., 2"),
        3: company(3, "ЗАО Пион", "Казань", "420000", "ул. Баумана, 3"),
        4: company(4, "ООО Сбой", "Тула", "300000", "ул. Ленина, 4"),
    }
    db["requisites"] = [
        # Пустые реквизиты, которые коробка создаёт вместе с компанией (ИНН null),
        # идут раньше заполненных — как на стенде 4-17-28.
        *(_empty_requisite(cid, cid) for cid in (1, 2, 3, 4)),
        requisite(11, 1, "7701234567", "770101001", "ООО Ромашка"),
        requisite(12, 2, "7702000002", "770201001", "ООО Лютик"),
        requisite(14, 4, "0000000000", "000001001", "ООО Сбой"),
    ]
    # 4-17-30: компания без ИНН, банковские реквизиты, лиды, товары с REF.
    db["companies"][5] = company(5, "ООО Без ИНН", "Тверь", "170000", "ул. Советская, 5")
    db["requisites"].append(_empty_requisite(5, 5))
    db["bankdetails"] = [
        _bank(21, 11, "044525225", "40702810400000000001", "ПАО Сбербанк"),
        _bank(22, 11, "044525593", "40702810500000000002", "АО Альфа-Банк"),
        _bank(23, 12, "044030653", "40702810600000000003", "ПАО Сбербанк СПб"),
    ]
    db["leads"] = {
        501: _lead(501, "NEW", 1),
        502: _lead(502, "CONVERTED", 2),
        503: _lead(503, "CONVERTED", 1),
        504: _lead(504, "CONVERTED", 5),
        505: _lead(505, "CONVERTED", 0),
        506: _lead(506, "CONVERTED", 4),  # SAP отклоняет ИНН 0000000000
        507: _lead(507, "CONVERTED", 2),  # второй успешный лид той же компании
    }
    # Каталог: товары с REF (свойство 61) и «текущим материалом» (62). R-300 нет в SAP,
    # 604 — товар без REF (услуга), 605 — REF есть, текущего материала нет (остатки).
    db["products"] = {
        601: _product(601, "Зонд А", "R-100"),
        602: _product(602, "Зонд Б", "R-200"),
        603: _product(603, "Зонд В", "R-300"),
        604: _product(604, "Монтаж", None),
    }
    db["prices"] = {}
    db["storeproducts"] = {}
    return db


# Стадии лидов: семантика — как в crm.status.list коробки (SEMANTICS S/F, пусто — в работе).
_LEAD_STATUSES = [
    {"STATUS_ID": "NEW", "ENTITY_ID": "STATUS", "NAME": "Новый", "SEMANTICS": None},
    {"STATUS_ID": "IN_PROCESS", "ENTITY_ID": "STATUS", "NAME": "В работе", "SEMANTICS": None},
    {"STATUS_ID": "CONVERTED", "ENTITY_ID": "STATUS", "NAME": "Качественный", "SEMANTICS": "S"},
    {"STATUS_ID": "JUNK", "ENTITY_ID": "STATUS", "NAME": "Некачественный", "SEMANTICS": "F"},
]
REF_PROPERTY = "property61"
CURMAT_PROPERTY = "property62"


def _lead(lid: int, status: str, company_id: int) -> dict[str, Any]:
    return {
        "ID": str(lid),
        "TITLE": f"Лид {lid}",
        "STATUS_ID": status,
        "COMPANY_ID": str(company_id),
    }


def _bank(bid: int, rid: int, bik: str, account: str, bank: str) -> dict[str, Any]:
    return {
        "ID": str(bid),
        "ENTITY_ID": str(rid),
        "NAME": bank,
        "RQ_BIK": bik,
        "RQ_ACC_NUM": account,
        "RQ_COR_ACC_NUM": "30101810400000000225",
        "RQ_BANK_NAME": bank,
        "COUNTRY_ID": "1",
    }


def _product(pid: int, name: str, ref: str | None) -> dict[str, Any]:
    return {
        "id": pid,
        "iblockId": 14,
        "name": name,
        REF_PROPERTY: {"valueId": pid * 10, "value": ref} if ref else None,
        CURMAT_PROPERTY: None,
    }


def _property_write(old: Any, value: Any, new_value_id: int) -> Any:
    """Запись свойства как в коробке: объект {value[, valueId]} — значение; строка или
    иной формат молча обнуляют свойство (ответ всё равно успешный)."""
    if not isinstance(value, dict) or "value" not in value:
        return None
    value_id = value.get("valueId") or (old or {}).get("valueId") or new_value_id
    return {"valueId": int(value_id), "value": value["value"]}


def _empty_requisite(rid: int, cid: int) -> dict[str, Any]:
    return {
        "ID": str(rid),
        "ENTITY_ID": str(cid),
        "ENTITY_TYPE_ID": "4",
        "PRESET_ID": "1",
        "RQ_INN": None,
        "RQ_KPP": None,
    }


def _match(items: Iterable[dict[str, Any]], filter_: Any) -> list[dict[str, Any]]:
    """Точное совпадение по ключам filter (сравнение строкой: form передаёт строки).

    Свойство товара (`propertyNN`) сравнивается по его значению `value`."""
    if not isinstance(filter_, dict) or not filter_:
        return list(items)

    def plain(value: Any) -> Any:
        return value.get("value") if isinstance(value, dict) else value

    return [
        item
        for item in items
        if all(str(plain(item.get(key))) == str(value) for key, value in filter_.items())
    ]


def _listish(value: Any) -> Any:
    """Form-список `{"0": a, "1": b}` → [a, b]; прочее — как есть."""
    if isinstance(value, dict) and value and all(k.isdigit() for k in value):
        return [value[k] for k in sorted(value, key=int)]
    return value


def _task_view(task: dict[str, Any]) -> dict[str, Any]:
    """Задача в ответе tasks.task.get/list: lowerCamel, как отдаёт портал."""
    return {
        "id": task["ID"],
        "title": task.get("TITLE", ""),
        "description": task.get("DESCRIPTION", ""),
        "status": task.get("STATUS", "2"),
        "responsibleId": task.get("RESPONSIBLE_ID"),
        "groupId": task.get("GROUP_ID", "0"),
        "deadline": task.get("DEADLINE"),
        "priority": task.get("PRIORITY", "1"),
        "tags": task.get("TAGS", []),
        "ufCrmTask": task.get("UF_CRM_TASK", []),
    }


def _stock_add(db: dict[str, Any], store_id: int, product_id: int, qty: float) -> None:
    """Проведение документа: изменить остаток (строка создаётся при первом движении)."""
    for row in db["storeproducts"].values():
        if int(row["storeId"]) == store_id and int(row["productId"]) == product_id:
            row["amount"] = float(row["amount"]) + qty
            return
    new_id = (max(db["storeproducts"]) if db["storeproducts"] else 0) + 1
    db["storeproducts"][new_id] = {
        "id": new_id,
        "storeId": store_id,
        "productId": product_id,
        "amount": qty,
        "quantityReserved": None,
    }


def create_app(
    limit_methods: frozenset[str] = frozenset(),
    extended: bool = False,
    v3_enabled: bool = True,
    v3_scope: bool = True,
    inventory_mode: bool = True,
) -> FastAPI:
    app = FastAPI(title="Bitrix24 Mock", version="0.1.0")
    db = _seed_extended() if extended else _seed()
    db["documents"] = {}
    db["tasks"] = {}
    db["task_chat"] = []
    db["task_forum"] = []
    db["im_messages"] = []
    limit_seen: dict[str, int] = {}
    failures: dict[str, dict[str, Any]] = {}

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
            # Коробка заводит пустой реквизит пресета «Организация» вместе с компанией.
            db["requisites"].append(_empty_requisite(len(db["requisites"]) + 100, new_id))
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
            for row in db["requisites"]:
                if row["ID"] == str(params["id"]):
                    row.update(fields)
            return {"result": True}
        if method == "crm.requisite.get":
            found = [r for r in db["requisites"] if r["ID"] == str(params["id"])]
            if not found:
                raise _BoxError("NOT_FOUND", "Not found")
            return {"result": found[0]}

        # --- банковские реквизиты, лиды, стадии (4-17-30) -------------------- #
        if method == "crm.requisite.bankdetail.list":
            entity_id = str(params.get("filter", {}).get("ENTITY_ID", ""))
            items = [
                b for b in db.get("bankdetails", []) if not entity_id or b["ENTITY_ID"] == entity_id
            ]
            page, nxt = _paginate(items, start)
            return _envelope(page, len(items), nxt)
        if method == "crm.requisite.bankdetail.get":
            found = [b for b in db.get("bankdetails", []) if b["ID"] == str(params["id"])]
            if not found:
                raise _BoxError("NOT_FOUND", "Not found")
            return {"result": found[0]}
        if method == "crm.requisite.bankdetail.add":
            new_id = 100 + len(db.setdefault("bankdetails", []))
            db["bankdetails"].append({"ID": str(new_id), **fields})
            return {"result": new_id}
        if method == "crm.lead.get":
            lead = db.get("leads", {}).get(int(params["id"]))
            if lead is None:
                raise _BoxError("NOT_FOUND", "Not found")
            return {"result": lead}
        if method == "crm.lead.update":
            db["leads"][int(params["id"])].update(fields)
            return {"result": True}
        if method == "crm.status.list":
            entity = str(params.get("filter", {}).get("ENTITY_ID", ""))
            items = [r for r in _LEAD_STATUSES if not entity or r["ENTITY_ID"] == entity]
            return _envelope(items, len(items), None)

        # --- каталог: товары ------------------------------------------------ #
        if method == "catalog.product.list":
            select = _listish(params.get("select")) or []
            missing = [f for f in ("id", "iblockId") if f not in select]
            if missing:
                raise _BoxError("0", "Required select fields: " + ", ".join(missing))
            items = _match(db["products"].values(), params.get("filter"))
            page, nxt = _paginate(items, start)
            # Как в коробке: только поля select (свойства — объектом {valueId, value}).
            page = [{k: v for k, v in p.items() if k in select} for p in page]
            return _wrapped({"products": page}, len(items), nxt)
        if method == "catalog.product.get":
            return {"result": {"product": db["products"].get(int(params["id"]), {})}}
        if method == "catalog.product.add":
            new_id = _next_id(db["products"])
            fields = {
                k: _property_write(None, v, new_id * 10) if k.startswith("property") else v
                for k, v in fields.items()
            }
            element = {"id": new_id, **fields}
            db["products"][new_id] = element
            return {"result": {"element": element}}
        if method == "catalog.product.update":
            product = db["products"][int(params["id"])]
            for key, value in fields.items():
                if key.startswith("property"):
                    value = _property_write(product.get(key), value, int(params["id"]) * 10)
                product[key] = value
            return {"result": {"element": db["products"][int(params["id"])]}}

        # --- каталог: цены -------------------------------------------------- #
        if method == "catalog.price.list":
            items = _match(db["prices"].values(), params.get("filter"))
            page, nxt = _paginate(items, start)
            return _wrapped({"prices": page}, len(items), nxt)
        if method == "catalog.price.add":
            new_id = _next_id(db["prices"])
            element = {"id": new_id, **fields}
            db["prices"][new_id] = element
            return {"result": {"price": element}}
        if method == "catalog.price.update":
            db["prices"][int(params["id"])].update(fields)
            return {"result": {"price": db["prices"][int(params["id"])]}}
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
            items = _match(db["storeproducts"].values(), params.get("filter"))
            page, nxt = _paginate(items, start)
            return _wrapped({"storeProducts": page}, len(items), nxt)
        if method == "catalog.storeproduct.get":
            return {"result": {"storeProduct": db["storeproducts"].get(int(params["id"]), {})}}
        if method in ("catalog.storeproduct.add", "catalog.storeproduct.update"):
            action = method.rsplit(".", 1)[1]
            raise _BoxError(
                "22002",
                f"Could not find description of {action} in "
                "Bitrix\\Catalog\\Controller\\StoreProduct",
            )

        # --- складской учёт: документы ------------------------------------ #
        if method == "catalog.document.mode.status":
            return {"result": "Y" if inventory_mode else "N"}
        if method == "catalog.document.add":
            if not fields.get("responsibleId"):
                raise _BoxError("0", "Required fields: responsibleId")
            new_id = _next_id(db["documents"])
            doc = {"id": new_id, "status": "N", "elements": [], **fields}
            db["documents"][new_id] = doc
            return {"result": {"document": {k: v for k, v in doc.items() if k != "elements"}}}
        if method == "catalog.document.element.add":
            doc = db["documents"][int(fields["docId"])]
            if doc["status"] != "N":
                raise _BoxError("0", "Документ уже проведён")
            doc["elements"].append(fields)
            return {"result": {"documentElement": {"id": len(doc["elements"]), **fields}}}
        if method in ("catalog.document.conduct", "catalog.document.cancel"):
            doc = db["documents"][int(params["id"])]
            sign = 1 if method.endswith("conduct") else -1
            for el in doc["elements"]:
                store = int(el.get("storeTo") or el.get("storeFrom"))
                qty = float(el["amount"]) * (1 if doc["docType"] == "S" else -1) * sign
                _stock_add(db, store, int(el["elementId"]), qty)
            doc["status"] = "Y" if sign == 1 else "C"
            return {"result": True}
        if method == "catalog.document.deleteList":
            for doc_id in _listish(params.get("documentIds")) or []:
                db["documents"].pop(int(doc_id), None)
            return {"result": True}

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

        # --- задачи (нотификатор) ----------------------------------------- #
        if method == "tasks.task.add":
            fail = failures.get(method)
            if fail and fail["times"] > 0 and not fail["after_store"]:
                fail["times"] -= 1
                raise _GatewayError()
            fields = {k: _listish(v) for k, v in (params.get("fields") or {}).items()}
            new_id = _next_id(db["tasks"])
            task = {"ID": str(new_id), "STATUS": "2", **fields}
            db["tasks"][new_id] = task
            if fail and fail["times"] > 0 and fail["after_store"]:
                # Задача сохранена, а ответ потерян (502 прокси) — исход для клиента неизвестен.
                fail["times"] -= 1
                raise _GatewayError()
            return {"result": {"task": _task_view(task)}}
        if method == "tasks.task.get":
            task = db["tasks"].get(int(params.get("taskId") or params.get("id")))
            if task is None:
                raise _MethodError(method)
            return {"result": {"task": _task_view(task)}}
        if method == "tasks.task.update":
            task = db["tasks"][int(params.get("taskId") or params.get("id"))]
            task.update({k: _listish(v) for k, v in (params.get("fields") or {}).items()})
            return {"result": {"task": _task_view(task)}}
        if method == "tasks.task.list":
            tag = (params.get("filter") or {}).get("TAG")
            tasks = [t for t in db["tasks"].values() if tag is None or tag in (t.get("TAGS") or [])]
            return {"result": {"tasks": [_task_view(t) for t in tasks]}}
        if method == "task.comment.add":
            task_id = int(params.get("taskId") or params.get("TASKID"))
            text = params.get("commentText") or (params.get("fields") or {}).get("POST_MESSAGE")
            db["task_forum"].append({"task_id": task_id, "text": text})
            return {"result": len(db["task_forum"])}
        if method == "im.message.add":
            db["im_messages"].append(
                {"dialog_id": params.get("DIALOG_ID"), "message": params.get("MESSAGE")}
            )
            return {"result": len(db["im_messages"])}

        raise _MethodError(method)

    @app.post("/rest/api/{user_id}/{token}/{method}")
    async def handle_v3(user_id: str, token: str, method: str, request: Request) -> JSONResponse:
        """REST v3: только JSON; чат задачи. Без v3 — как портал старой версии."""
        if not v3_enabled or method != "tasks.task.chat.message.send":
            return JSONResponse(
                status_code=404,
                content={"error": "ERROR_METHOD_NOT_FOUND", "error_description": method},
            )
        if not v3_scope:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "BITRIX_REST_V3_EXCEPTION_INSUFFICIENTSCOPEEXCEPTION",
                        "message": "Недостаточно прав доступа: отсутствует необходимый scope.",
                    }
                },
            )
        body = await request.json()
        fields = body.get("fields") or {}
        task_id = int(fields.get("taskId") or 0)
        if task_id not in db["tasks"]:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "BITRIX_TASKS_TASK_NOT_FOUND",
                        "message": "Задача не найдена",
                        "validation": [{"field": "taskId", "message": "нет задачи"}],
                    }
                },
            )
        db["task_chat"].append({"task_id": task_id, "text": fields.get("text")})
        return JSONResponse({"result": {"result": True}})

    @app.post("/_fail")
    async def inject_failure(request: Request) -> JSONResponse:
        """Тестовый хук: следующие `times` вызовов `method` отвечают 502 как nginx-прокси.

        after_store=true — задача сохраняется, но ответ теряется (исход неизвестен).
        """
        body = await request.json()
        failures[str(body["method"])] = {
            "times": int(body.get("times", 1)),
            "after_store": bool(body.get("after_store", False)),
        }
        return JSONResponse({"ok": True})

    @app.post("/_tasks/{task_id}/status")
    async def set_task_status(task_id: int, request: Request) -> JSONResponse:
        """Тестовый хук: сменить статус задачи (5 — завершена)."""
        body = await request.json()
        db["tasks"][task_id]["STATUS"] = str(body.get("status", 5))
        return JSONResponse({"ok": True})

    @app.get("/_state")
    async def state() -> JSONResponse:
        """Состояние мока для проверок e2e (мок живёт в отдельном процессе)."""
        return JSONResponse(
            {
                name: list(store.values()) if isinstance(store, dict) else store
                for name, store in db.items()
            }
        )

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

        # /_fail для прочих методов (у tasks.task.add — своя логика after_store).
        fail = failures.get(method)
        if method != "tasks.task.add" and fail and fail["times"] > 0:
            fail["times"] -= 1
            return HTMLResponse("<html><body>502 Bad Gateway</body></html>", status_code=502)

        try:
            return JSONResponse(_dispatch(method, params))
        except _GatewayError:
            return HTMLResponse("<html><body>502 Bad Gateway</body></html>", status_code=502)
        except _MethodError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": "ERROR_METHOD_NOT_FOUND", "error_description": str(exc)},
            )
        except _BoxError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": exc.code, "error_description": exc.description},
            )

    return app


class _MethodError(RuntimeError):
    pass


class _BoxError(RuntimeError):
    """Ошибка метода в конверте коробки `{"error": код, "error_description": …}`."""

    def __init__(self, code: str, description: str) -> None:
        super().__init__(description)
        self.code = code
        self.description = description


class _GatewayError(RuntimeError):
    """Имитация 502 от nginx перед порталом."""


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
        except (_MethodError, _BoxError) as exc:
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
