"""Проверки сводок услуг на вымышленных визитах."""

import unittest

from sqlalchemy import create_engine, text

from analytics.services import build_service_report


class ServiceReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE visits (
                    visit_id INTEGER PRIMARY KEY, patient_id TEXT, visit_date DATE, total_sum REAL
                )
            """))
            connection.execute(text("""
                CREATE TABLE visit_items (
                    visit_id INTEGER, service_name TEXT, category TEXT, qty REAL, price REAL,
                    "sum" REAL, discount REAL
                )
            """))
            connection.execute(text("CREATE TABLE patients (patient_id TEXT PRIMARY KEY, ltv_hist REAL)"))
            connection.exec_driver_sql(
                "INSERT INTO visits VALUES (?, ?, ?, ?)",
                [
                    (1, "a", "2026-01-01", 140), (2, "a", "2026-01-02", 100),
                    (3, "a", "2026-01-03", 0), (4, "a", "2026-01-04", 40),
                    (5, "a", "2026-01-05", 50), (6, "a", "2026-01-06", 50),
                    (8, "b", "2026-01-01", 0), (7, "b", "2026-01-01", 30),
                    (9, "c", "2026-01-01", 10), (10, "e", None, 15),
                    (11, "e", "2026-01-01", 10),
                ],
            )
            connection.exec_driver_sql(
                "INSERT INTO visit_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (1, "А-Снимок", "Диагностика", 1, 50, 40, 10),
                    (1, "Лечение", "Терапия", 2, 60, 100, 20),
                    (2, "Гигиена", "Гигиена", 1, 100, 80, 20),
                    (2, "З-Лечение", "Терапия", 1, 20, 20, 0),
                    (4, "Материал", "Прочее", 2, 25, 40, 10),
                    (5, "Гигиена", "Гигиена", 1, 100, 40, 60),
                    (5, "Лечение", "Терапия", 1, 40, 40, 0),
                    (5, "Гигиена", "Гигиена", 1, 100, -30, 130),
                    (6, "Сторно количества", "Прочее", -1, 20, 20, 0),
                    (6, "Лечение", "Терапия", 1, 30, 30, 0),
                    (7, "Лечение", "Терапия", 1, 30, 30, 0),
                    (8, "Гигиена", "Гигиена", 1, 50, 0, 50),
                    (9, "Неизвестная", None, 1, None, 10, None),
                    (9, "Дополнение", "Новая категория", None, 0, 0, 0),
                    (10, "Материал", "Прочее", 1, 15, 15, 0),
                    (11, "Лечение", "Терапия", 1, 10, 10, 0),
                ],
            )
            connection.exec_driver_sql(
                "INSERT INTO patients VALUES (?, ?)", [("a", 380), ("b", 30), ("c", None), ("d", 0), ("e", 25)],
            )

    def test_revenue_quantities_and_discounts(self):
        report = build_service_report(self.engine)
        categories = {row["category"]: row for row in report["categories"]}
        self.assertEqual({key: row["revenue"] for key, row in categories.items()}, {
            "Терапия": 230, "Гигиена": 90, "Прочее": 75, "Диагностика": 40, None: 10,
        })
        self.assertEqual(sum(row["revenue"] for row in categories.values()), 445)
        self.assertAlmostEqual(sum(row["revenue_share"] for row in categories.values()), 1)
        self.assertEqual(categories["Терапия"]["qty"], 7)
        self.assertEqual(categories["Гигиена"]["qty"], 3)
        self.assertEqual(categories["Гигиена"]["discount"], 130)
        self.assertEqual(categories["Гигиена"]["negative_amount"], 30)
        self.assertEqual(categories[None]["n_unknown_discount"], 2)
        self.assertEqual(categories[None]["n_unknown_qty"], 1)
        self.assertEqual(report["totals"]["discount"], 170)
        self.assertEqual(report["totals"]["n_adjustment_rows"], 2)
        self.assertEqual(report["other"]["summary"], categories["Прочее"])
        self.assertEqual([row["service_name"] for row in report["other"]["services"]], [
            "Материал", "Сторно количества",
        ])
        self.assertTrue(report["reconciliation"]["items_match_visits"])
        self.assertTrue(report["reconciliation"]["categories_match_items"])
        self.assertEqual(report["reconciliation"]["n_visit_total_mismatches"], 0)

    def test_ltv_uses_one_first_service_and_counts_missing_ltv(self):
        report = build_service_report(self.engine)
        ltv = {row["category"]: row for row in report["ltv_by_first_category"]}
        self.assertEqual(ltv["Диагностика"]["avg_ltv_hist"], 380)
        self.assertEqual(ltv["Терапия"]["avg_ltv_hist"], 30)
        self.assertEqual(ltv[None]["n_patients"], 3)
        self.assertEqual(ltv[None]["n_with_ltv"], 2)
        self.assertEqual(ltv[None]["avg_ltv_hist"], 12.5)
        self.assertEqual(sum(row["n_patients"] for row in ltv.values()), 5)
        self.assertEqual(sum(row["ltv_hist"] for row in ltv.values()), 435)

    def test_adjacent_visits_yield_at_most_one_transition(self):
        report = build_service_report(self.engine)
        pairs = {(row["from_category"], row["to_category"]): row for row in report["transitions"]}
        self.assertEqual({key: row["n_transitions"] for key, row in pairs.items()}, {
            ("Терапия", "Гигиена"): 2, ("Прочее", "Гигиена"): 1, ("Гигиена", "Терапия"): 1,
        })
        self.assertEqual(pairs["Терапия", "Гигиена"]["n_patients"], 2)
        self.assertTrue(all(row["transition_share"] == 1 for row in pairs.values()))
        self.assertEqual(report["transition_coverage"], {
            "candidate_pairs": 6, "skipped_pairs": 2, "n_undated_histories": 1,
        })

    def test_repeated_pair_counts_visits_and_patients_separately(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO visits VALUES (?, ?, ?, ?)", [
                (12, "b", "2026-01-02", 30), (13, "b", "2026-01-03", 0), (14, "b", "2026-01-04", 30),
            ])
            connection.exec_driver_sql("INSERT INTO visit_items VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (12, "Лечение", "Терапия", 1, 30, 30, 0), (13, "Гигиена", "Гигиена", 1, 50, 0, 50),
                (14, "Материал", "Прочее", 1, 30, 30, 0),
            ])
        report = build_service_report(self.engine)
        pairs = {(row["from_category"], row["to_category"]): row for row in report["transitions"]}
        self.assertEqual(pairs["Терапия", "Гигиена"]["n_transitions"], 3)
        self.assertEqual(pairs["Терапия", "Гигиена"]["n_patients"], 2)
        self.assertEqual(pairs["Гигиена", "Терапия"]["n_transitions"], 2)
        self.assertEqual(pairs["Гигиена", "Терапия"]["n_patients"], 2)
        self.assertAlmostEqual(pairs["Гигиена", "Терапия"]["transition_share"], 2 / 3)
        self.assertAlmostEqual(pairs["Гигиена", "Прочее"]["transition_share"], 1 / 3)

    def test_reconciliation_detects_errors_cancelling_in_total(self):
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE visits SET total_sum = total_sum + 1 WHERE visit_id = 1"))
            connection.execute(text("UPDATE visits SET total_sum = total_sum - 1 WHERE visit_id = 2"))
        reconciliation = build_service_report(self.engine)["reconciliation"]
        self.assertTrue(reconciliation["items_match_visits"])
        self.assertEqual(reconciliation["n_visit_total_mismatches"], 2)
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE visits SET total_sum = total_sum + 1 WHERE visit_id = 1"))
        reconciliation = build_service_report(self.engine)["reconciliation"]
        self.assertFalse(reconciliation["items_match_visits"])
        self.assertEqual(reconciliation["items_minus_visits"], -1)

    def test_zero_revenue_has_no_share(self):
        with self.engine.begin() as connection:
            connection.execute(text('UPDATE visit_items SET "sum" = 0'))
            connection.execute(text("UPDATE visits SET total_sum = 0"))
        report = build_service_report(self.engine)
        self.assertTrue(all(row["revenue_share"] is None for row in report["categories"]))
        self.assertTrue(report["reconciliation"]["items_match_visits"])
