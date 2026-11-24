"""Слой доступа к данным.

Все экраны и API берут данные только отсюда. Источник выбирается автоматически:
- если в базе (DATABASE_URL) есть таблицы контракта — читаем базу;
- иначе — фейковые данные из fixtures.py.
Так можно работать до того, как etl/, analytics/ и offers/ отдадут свои таблицы.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from app import config, fixtures

CONTRACT_TABLES = ["visits", "visit_items", "services", "patients", "offers", "comment_tags"]
REQUIRED_TABLES = ["visits", "visit_items", "patients"]  # без них база бесполезна


@lru_cache
def engine():
    return create_engine(config.DATABASE_URL, future=True)


def _db_tables() -> set[str]:
    try:
        return set(inspect(engine()).get_table_names())
    except Exception:
        return set()


def source() -> str:
    """'db' или 'fixtures'."""
    if config.USE_FIXTURES == "true":
        return "fixtures"
    if config.USE_FIXTURES == "false":
        return "db"
    return "db" if set(REQUIRED_TABLES) <= _db_tables() else "fixtures"


@lru_cache
def _fixtures() -> dict[str, pd.DataFrame]:
    return fixtures.build()


def table(name: str) -> pd.DataFrame:
    """Таблица контракта целиком. Пустой DataFrame, если таблицы ещё нет."""
    if source() == "fixtures":
        return _fixtures().get(name, pd.DataFrame()).copy()
    if name not in _db_tables():
        return pd.DataFrame()
    return pd.read_sql_table(name, engine())


def reset_cache() -> None:
    """Сбросить кэш после загрузки новых данных."""
    _fixtures.cache_clear()


# ---------- contacts: единственная таблица, которую пишет app ----------

_memory_contacts: list[dict] = []


def _contacts_ddl() -> str:
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if engine().dialect.name == "sqlite" else "SERIAL PRIMARY KEY"
    return (f"CREATE TABLE IF NOT EXISTS contacts (contact_id {pk}, patient_id TEXT NOT NULL, "
            "offer_id TEXT, result TEXT NOT NULL, note TEXT, created_at TIMESTAMP NOT NULL)")


def add_contact(patient_id: str, result: str, offer_id: str | None = None, note: str | None = None) -> dict:
    row = {"patient_id": patient_id, "offer_id": offer_id, "result": result,
           "note": note or "", "created_at": datetime.now()}
    if source() == "fixtures":
        row["contact_id"] = len(_memory_contacts) + 1
        _memory_contacts.append(row)
        return row
    with engine().begin() as con:
        con.execute(text(_contacts_ddl()))
        con.execute(text("INSERT INTO contacts (patient_id, offer_id, result, note, created_at) "
                         "VALUES (:patient_id, :offer_id, :result, :note, :created_at)"), row)
    return row


def contacts(patient_id: str | None = None) -> pd.DataFrame:
    if source() == "fixtures":
        df = pd.DataFrame(_memory_contacts, columns=["contact_id", "patient_id", "offer_id", "result", "note", "created_at"])
    elif "contacts" in _db_tables():
        df = pd.read_sql_table("contacts", engine())
    else:
        return pd.DataFrame(columns=["contact_id", "patient_id", "offer_id", "result", "note", "created_at"])
    if patient_id:
        df = df[df.patient_id == patient_id]
    return df.sort_values("created_at", ascending=False)
