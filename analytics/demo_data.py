"""Вымышленные визиты для ноутбука и локальной демонстрации аналитики."""

import sqlite3
from hashlib import sha1


def create_demo_db(*, extended: bool = False) -> sqlite3.Connection:
    """Возвращает SQLite в памяти. Дополнительные визиты нужны для графиков."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE services (
            service_name TEXT PRIMARY KEY, category TEXT, follow_up_days INTEGER, is_chain_start BOOLEAN
        );
        CREATE TABLE visits (
            visit_id INTEGER PRIMARY KEY, visit_date DATE, patient_id TEXT,
            last_name TEXT, first_name TEXT, gender TEXT, author TEXT, comment TEXT,
            total_sum REAL, has_services BOOLEAN, source_file TEXT
        );
        CREATE TABLE visit_items (
            visit_id INTEGER REFERENCES visits(visit_id),
            service_name TEXT REFERENCES services(service_name),
            category TEXT, doctor TEXT, qty REAL, price REAL, "sum" REAL, discount REAL
        );
        CREATE TABLE patients (
            patient_id TEXT PRIMARY KEY, last_name TEXT, first_name TEXT, gender TEXT,
            first_visit DATE, last_visit DATE, n_visits INTEGER, n_paid_visits INTEGER,
            revenue REAL, avg_check REAL, days_since_last INTEGER, categories TEXT,
            main_doctor TEXT, is_child BOOLEAN, segment TEXT, rfm TEXT,
            ltv_hist REAL, ltv_pred REAL
        );
    """)

    service_rows = [
        ("Тестовая гигиена", "Гигиена", 180, False),
        ("Тестовый снимок", "Диагностика", None, False),
        ("Тестовая консультация", "Консультация", None, False),
    ]
    categories_by_service = {name: category for name, category, _, _ in service_rows}

    # Номер пациента, дата, комментарий и услуги (название, количество, цена, сумма).
    visit_rows = [
        (1, "2026-01-10", "", [("Тестовая гигиена", 1, 3000, 2800), ("Тестовый снимок", 1, 700, 700)]),
        (1, "2026-02-10", "", [("Тестовая гигиена", 1, 2000, 2000)]),
        (2, "2026-01-14", "", [("Тестовая гигиена", 1, 2500, 2500)]),
        (2, "2026-02-12", "Повторная запись", []),
        (3, "2026-01-20", "", [("Тестовый снимок", 1, 1300, 1300)]),
        (4, "2026-02-15", "", [("Тестовый снимок", 1, 700, 700)]),
        (5, "2026-01-25", "Перенос записи", []),
        (5, "2026-02-20", "", [("Тестовая консультация", 1, 500, 0)]),
    ]
    if extended:
        visit_rows.extend([
            (6, "2025-10-01", "", [("Тестовый снимок", 1, 3500, 3500)]),
            (6, "2025-11-01", "", [("Тестовая гигиена", 1, 3500, 3500)]),
            (6, "2026-01-15", "", [("Тестовый снимок", 1, 3500, 3500)]),
            (6, "2026-07-15", "", [("Тестовая гигиена", 1, 3500, 3500)]),
            (7, "2025-10-05", "", [("Тестовый снимок", 1, 1200, 1200)]),
            (7, "2025-10-22", "", [("Тестовый снимок", 1, 1800, 1800)]),
            (8, "2025-11-10", "", [("Тестовый снимок", 1, 2000, 2000)]),
            (9, "2026-01-05", "", [("Тестовый снимок", 1, 1200, 1200)]),
            (9, "2026-02-07", "", [("Тестовая гигиена", 1, 2000, 2000)]),
            (9, "2026-03-10", "", [("Тестовый снимок", 1, 1500, 1500)]),
            (10, "2026-07-25", "", [("Тестовая гигиена", 1, 2000, 2000)]),
            (11, "2026-05-07", "", [("Тестовая гигиена", 1, 2000, 2000)]),
            (11, "2026-07-07", "", [("Тестовая гигиена", 1, 2000, 2000)]),
            (12, "2026-08-01", "", [("Тестовая консультация", 1, 500, 0)]),
            (13, "2025-10-08", "", [("Тестовая гигиена", 1, 1500, 1500)]),
            (13, "2025-10-09", "", [("Тестовая гигиена", 1, 1500, 1500)]),
        ])

    with db:
        db.executemany("INSERT INTO services VALUES (?, ?, ?, ?)", service_rows)
        for visit_id, (patient_number, visit_date, comment, items) in enumerate(visit_rows, start=1):
            last_name = f"Тестовая фамилия {patient_number}"
            first_name = f"Тестовое имя {patient_number}"
            normalized_name = f"{last_name.strip()}|{first_name.strip()}".lower().replace("ё", "е")
            patient_id = sha1(normalized_name.encode("utf-8")).hexdigest()[:12]
            db.execute(
                "INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    visit_id, visit_date, patient_id, last_name, first_name, "unknown",
                    "Тестовый администратор", comment, sum(item[3] for item in items),
                    bool(items), f"synthetic_{visit_id}.xls",
                ),
            )
            db.executemany(
                "INSERT INTO visit_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (visit_id, name, categories_by_service[name], "Тестовый Врач", qty, price, amount,
                     max(0, qty * price - amount))
                    for name, qty, price, amount in items
                ],
            )

        # Сначала считаем визиты, чтобы визит с двумя услугами учёлся один раз.
        db.execute("""
            WITH visit_totals AS (
                SELECT patient_id, last_name, first_name, gender,
                       MIN(visit_date) AS first_visit, MAX(visit_date) AS last_visit,
                       COUNT(*) AS n_visits,
                       COUNT(CASE WHEN has_services AND total_sum > 0 THEN 1 END) AS n_paid_visits,
                       SUM(total_sum) AS revenue
                FROM visits
                GROUP BY patient_id, last_name, first_name, gender
            ),
            service_details AS (
                SELECT visits.patient_id, GROUP_CONCAT(DISTINCT category) AS categories,
                       MAX(doctor) AS main_doctor,
                       MAX(category = 'Детская') AS is_child
                FROM visits
                JOIN visit_items USING (visit_id)
                GROUP BY visits.patient_id
            )
            INSERT INTO patients (
                patient_id, last_name, first_name, gender, first_visit, last_visit, n_visits,
                n_paid_visits, revenue, avg_check, days_since_last, categories, main_doctor, is_child
            )
            SELECT patient_id, last_name, first_name, gender, first_visit, last_visit, n_visits,
                   n_paid_visits, revenue, revenue / NULLIF(n_paid_visits, 0),
                   CAST(JULIANDAY((SELECT MAX(visit_date) FROM visits)) - JULIANDAY(last_visit) AS INTEGER),
                   COALESCE(categories, ''), main_doctor, COALESCE(is_child, 0)
            FROM visit_totals
            LEFT JOIN service_details USING (patient_id)
        """)
    return db
