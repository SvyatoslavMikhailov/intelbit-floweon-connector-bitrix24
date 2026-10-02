"""Базовый пример: подключение + чтение компаний и каталога.

Запуск: BITRIX_WEBHOOK_URL=... uv run python examples/basic_usage.py
"""

from __future__ import annotations

import asyncio
import os

from intelbit_floweon_connector_bitrix24 import Bitrix24Connector


async def main() -> None:
    connector = Bitrix24Connector(
        {
            "webhook_base_url": os.environ["BITRIX_WEBHOOK_URL"],
            "iblock_id": int(os.environ.get("BITRIX_IBLOCK_ID", "0")) or None,
            "price_type_id": int(os.environ.get("BITRIX_PRICE_TYPE_ID", "0")) or None,
            "rate_limit_rps": 2,
        }
    )
    await connector.start()

    # Контрагенты с реквизитами (ИНН/КПП)
    companies = await connector.read("company", {"select": ["ID", "TITLE"]})
    print(f"Контрагентов: {len(companies)}")
    for company in companies[:5]:
        inn_kpp = await connector.companies.get_inn_kpp(company["id"])
        print(f"  {company.get('title')} — ИНН {inn_kpp['inn']} / КПП {inn_kpp['kpp']}")

    # Каталог товаров
    products = await connector.read("product", {})
    print(f"Товаров: {len(products)}")

    health = await connector.health_check()
    print(f"health: {health.healthy} {health.message}")
    await connector.stop()


if __name__ == "__main__":
    asyncio.run(main())
