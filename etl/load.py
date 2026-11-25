"""Инкрементальная загрузка визитов в локальную SQLite и выгрузка CSV."""

import argparse
import csv
import os
from collections import defaultdict
from datetime import date
from math import fsum
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, text
from xlrd import XLRDError

from .categories import FOLLOW_UP_DAYS, categorize, is_chain_start
from .parse import parse_file
from .patients import build_patients


SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS visits (
        visit_id INTEGER PRIMARY KEY, visit_date DATE, patient_id TEXT,
        last_name TEXT, first_name TEXT, gender TEXT, author TEXT,
        comment TEXT, total_sum REAL, has_services BOOLEAN, source_file TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS visit_items (
        visit_id INTEGER NOT NULL REFERENCES visits(visit_id),
        service_name TEXT, category TEXT, doctor TEXT, qty REAL,
        price REAL, "sum" REAL, discount REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS services (
        service_name TEXT PRIMARY KEY NOT NULL, category TEXT NOT NULL,
        follow_up_days INTEGER, is_chain_start BOOLEAN NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY NOT NULL, last_name TEXT, first_name TEXT,
        gender TEXT, first_visit DATE, last_visit DATE, n_visits INTEGER,
        n_paid_visits INTEGER, revenue REAL, avg_check REAL, days_since_last INTEGER,
        categories TEXT, main_doctor TEXT, is_child BOOLEAN, segment TEXT, rfm TEXT,
        ltv_hist REAL, ltv_pred REAL
    )
    """,
)


def write_rows(connection, table, rows, key=None):
    if not rows:
        return
    columns = ", ".join(f'"{column}"' for column in rows[0])
    values = ", ".join(f":{column}" for column in rows[0])
    statement = f"INSERT INTO {table} ({columns}) VALUES ({values})"
    if key:
        updates = ", ".join(
            f'"{column}" = excluded."{column}"' for column in rows[0] if column != key
        )
        statement += f" ON CONFLICT ({key}) DO UPDATE SET {updates}"
    connection.execute(text(statement), rows)


def load(source, report_date=None):
    paths = sorted(source.glob("*.xls"))
    if not paths:
        raise ValueError("В указанной папке нет файлов .xls.")

    incoming = {}
    errors = []
    for path in paths:
        try:
            visit, items = parse_file(path)
            visit_id = visit["visit_id"]
            if visit_id in incoming:
                raise ValueError(f"Повторяющийся visit_id: {visit_id}")
            incoming[visit_id] = visit, items
        except (ValueError, KeyError, IndexError, OSError, TypeError, XLRDError) as error:
            errors.append(f"{path.name}: {error}")

    if errors:
        raise ValueError(
            f"Файлов обработано {len(paths)}, с ошибками {len(errors)}, загружено 0. "
            + "\n".join(errors)
        )

    engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///data/ilfa.db"))
    if engine.dialect.name != "sqlite" or engine.url.database in (None, "", ":memory:"):
        raise ValueError("Для локальной загрузки нужен URL SQLite с путём к файлу.")
    output_dir = Path(engine.url.database).parent

    with TemporaryDirectory(dir=output_dir) as tmp:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            for statement in SCHEMA:
                connection.exec_driver_sql(statement)

            existing = set(connection.exec_driver_sql("SELECT visit_id FROM visits").scalars())
            new_visits = []
            new_items = []
            for visit_id, (visit, items) in incoming.items():
                if visit_id not in existing:
                    new_visits.append(visit)
                    new_items.extend(items)
            write_rows(connection, "visits", new_visits)
            write_rows(connection, "visit_items", new_items)

            visits = list(connection.exec_driver_sql("SELECT * FROM visits ORDER BY visit_id").mappings())
            items = list(connection.exec_driver_sql("SELECT * FROM visit_items ORDER BY rowid").mappings())
            genders = defaultdict(set)
            for visit in visits:
                if visit["gender"] != "unknown":
                    genders[visit["patient_id"]].add(visit["gender"])
            recovered = [
                {"visit_id": visit["visit_id"], "gender": next(iter(genders[visit["patient_id"]]))}
                for visit in visits
                if visit["gender"] == "unknown" and len(genders[visit["patient_id"]]) == 1
            ]
            if recovered:
                connection.execute(text("UPDATE visits SET gender = :gender WHERE visit_id = :visit_id"), recovered)
                visits = list(connection.exec_driver_sql("SELECT * FROM visits ORDER BY visit_id").mappings())

            services = []
            for name in sorted({item["service_name"] for item in items}):
                category = categorize(name)
                services.append({
                    "service_name": name,
                    "category": category,
                    "follow_up_days": FOLLOW_UP_DAYS.get(category),
                    "is_chain_start": is_chain_start(name),
                })
            write_rows(connection, "services", services, "service_name")
            connection.exec_driver_sql("""
                UPDATE visit_items SET category = (
                    SELECT category FROM services WHERE services.service_name = visit_items.service_name
                )
                WHERE category IS NOT (SELECT category FROM services WHERE services.service_name = visit_items.service_name)
            """)
            items = list(connection.exec_driver_sql("SELECT * FROM visit_items ORDER BY rowid").mappings())
            patients = build_patients(visits, items, report_date)
            write_rows(connection, "patients", patients, "patient_id")

            tables = {"visits": visits, "visit_items": items}
            for table, rows in tables.items():
                fields = list(connection.exec_driver_sql(f"SELECT * FROM {table} LIMIT 0").keys())
                with (Path(tmp) / f"{table}.csv").open("w", encoding="utf-8", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=fields)
                    writer.writeheader()
                    if table == "visits":
                        writer.writerows(dict(row, has_services=bool(row["has_services"])) for row in rows)
                    else:
                        writer.writerows(rows)

        for table in tables:
            (Path(tmp) / f"{table}.csv").replace(output_dir / f"{table}.csv")

    revenue = fsum(item["sum"] for item in items)
    print(f"Файлов обработано {len(paths)}, новых визитов {len(new_visits)}, "
          f"пропущено известных {len(paths) - len(new_visits)}, с ошибками 0.")
    print(f"В базе визитов {len(visits)}, строк услуг {len(items)}, "
          f"пациентов {len(patients)}, выручка {revenue:.2f} ₽.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Папка с файлами .xls")
    parser.add_argument("--report-date", type=date.fromisoformat, help="Дата отчёта в формате ГГГГ-ММ-ДД")
    args = parser.parse_args()
    try:
        load(args.source, args.report_date)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
