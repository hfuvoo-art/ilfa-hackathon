"""Граничные случаи контракта и атомарности на вымышленных данных."""

import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from analytics.demo_data import create_demo_db
from analytics.ltv import VisitHistory, calculate_ltv, summarize_ltv
from analytics.segments import Patient, _business_segment, _has_unfinished_treatment, compute_segments


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', creator=create_demo_db, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)

    def snapshot(self):
        with self.engine.connect() as conn:
            return {table: conn.exec_driver_sql(f'SELECT * FROM {table} ORDER BY 1').all()
                    for table in ('patients', 'visits', 'visit_items', 'services')}

    def test_offsetting_patient_revenue_errors_are_rejected(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE patients SET revenue = revenue + CASE WHEN revenue = 5500 THEN 100 ELSE -100 END WHERE revenue IN (5500, 2500)')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            compute_segments(self.engine)
        self.assertEqual(self.snapshot(), before)

    def test_stale_visit_counts_are_rejected(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE patients SET n_paid_visits = n_paid_visits + 1')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            compute_segments(self.engine)
        self.assertEqual(self.snapshot(), before)

    def test_zero_value_visit_without_patient_is_rejected(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO visits (visit_id, patient_id, visit_date, total_sum, has_services) VALUES (99, 'synthetic-orphan', '2026-01-01', 0, 0)")
        with self.assertRaises(ValueError):
            compute_segments(self.engine)

    def test_refund_preserves_historical_total(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE visits SET total_sum = -700 WHERE visit_id = 6')
            conn.exec_driver_sql('UPDATE patients SET revenue = -700, n_paid_visits = 0 WHERE revenue = 700')
        compute_segments(self.engine)
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql('SELECT ltv_hist, ltv_pred FROM patients WHERE revenue = -700').one()
            self.assertEqual(tuple(row), (-700, 0))
            self.assertEqual(conn.exec_driver_sql('SELECT SUM(ltv_hist) FROM patients').scalar_one(), 8600)

    def test_failure_during_updates_rolls_back_all_fields(self):
        compute_segments(self.engine)
        with self.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE patients SET segment = 'before', rfm = 'before', ltv_hist = 7, ltv_pred = 8")
            conn.exec_driver_sql("""CREATE TRIGGER fail_update BEFORE UPDATE OF segment ON patients
                WHEN OLD.revenue = 700 BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        before = self.snapshot()
        with self.assertRaises(SQLAlchemyError):
            compute_segments(self.engine)
        self.assertEqual(self.snapshot(), before)

    def test_only_four_analytics_fields_change(self):
        before = self.snapshot()
        compute_segments(self.engine)
        after = self.snapshot()
        for table in ('visits', 'visit_items', 'services'):
            self.assertEqual(before[table], after[table])
        self.assertEqual([tuple(row)[:-4] for row in before['patients']],
                         [tuple(row)[:-4] for row in after['patients']])

    def test_missing_metrics_fall_back_to_visit_history(self):
        expected = compute_segments(self.engine)
        with self.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE patients SET revenue = NULL, n_visits = NULL, n_paid_visits = NULL, first_visit = NULL, last_visit = NULL, days_since_last = NULL')
        self.assertEqual(compute_segments(self.engine), expected)

    def test_empty_database(self):
        with self.engine.begin() as conn:
            for table in ('visit_items', 'visits', 'patients', 'services'):
                conn.exec_driver_sql(f'DELETE FROM {table}')
        self.assertEqual(compute_segments(self.engine), {})

    def test_first_service_excludes_adjustments_and_zero_quantity(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql('DELETE FROM visit_items')
            conn.exec_driver_sql("INSERT INTO services (service_name, category) VALUES (?, 'Гигиена')", [
                ('А-Возврат',), ('Б-Сторно',), ('В-Корректировка цены',),
                ('Г-Нулевое количество',), ('Д-Первая услуга',),
            ])
            patient_id = conn.exec_driver_sql('SELECT patient_id FROM visits WHERE visit_id = 1').scalar_one()
            conn.exec_driver_sql('DELETE FROM patients WHERE patient_id != ?', (patient_id,))
            conn.exec_driver_sql('''INSERT INTO visit_items
                (visit_id, service_name, category, qty, price, "sum", discount)
                VALUES (?, ?, 'Гигиена', ?, ?, ?, 0)''', [
                    (1, 'А-Возврат', 1, 100, -100),
                    (1, 'Б-Сторно', -1, 100, 100),
                    (1, 'В-Корректировка цены', 1, -100, 100),
                    (1, 'Г-Нулевое количество', 0, 100, 100),
                    (1, 'Д-Первая услуга', 1, 100, 100),
                ])
            rows = summarize_ltv(conn)['by_first_service']
            self.assertEqual([(row['service_name'], row['n_patients']) for row in rows],
                             [('Д-Первая услуга', 1)])

    def test_undated_service_makes_first_service_unknown(self):
        with self.engine.begin() as conn:
            patient_id = conn.exec_driver_sql('SELECT patient_id FROM visits WHERE visit_id = 1').scalar_one()
            conn.exec_driver_sql('DELETE FROM patients WHERE patient_id != ?', (patient_id,))
            conn.exec_driver_sql('UPDATE visits SET visit_date = NULL WHERE visit_id = 1')
            rows = summarize_ltv(conn)['by_first_service']
            self.assertEqual([(row['service_name'], row['n_patients']) for row in rows], [(None, 1)])


class BoundaryTests(unittest.TestCase):
    reference = date(2026, 9, 30)

    def segment(self, *, age=200, recency=80, visits=2, paid=2, revenue=100,
                child=False, hygiene=False, events=None):
        patient = Patient('synthetic', self.reference - timedelta(days=age),
                          self.reference - timedelta(days=recency), recency,
                          visits, paid, revenue, child)
        return _business_segment(patient, 1000, {'synthetic'} if hygiene else set(),
                                 {'synthetic': events or {}}, self.reference)

    def test_all_eight_segments_and_cutoffs(self):
        cases = [
            ({'paid': 3, 'visits': 3, 'revenue': 1000, 'recency': 180}, 'Ценные лояльные'),
            ({'age': 60, 'recency': 60}, 'Новые'),
            ({'age': 61, 'recency': 61}, 'Активные'),
            ({'visits': 1, 'paid': 1, 'recency': 90}, 'Активные'),
            ({'visits': 1, 'paid': 1, 'recency': 91}, 'Пропал после 1 визита'),
            ({'recency': 181}, 'Спящие'),
            ({'recency': 180}, 'Активные'),
            ({'hygiene': True, 'recency': 181}, 'Только гигиена'),
            ({'child': True}, 'Дети и семьи'),
            ({'events': {'implant_installation': date(2026, 1, 1)}}, 'Незавершённое лечение'),
        ]
        for kwargs, expected in cases:
            with self.subTest(expected=expected, inputs=kwargs):
                self.assertEqual(self.segment(**kwargs), expected)

    def test_loyal_and_new_have_priority_over_treatment(self):
        events = {'implant_installation': date(2026, 1, 1)}
        self.assertEqual(self.segment(paid=3, visits=3, revenue=1000, events=events), 'Ценные лояльные')
        self.assertEqual(self.segment(age=30, recency=20, events=events), 'Новые')

    def test_chain_completion_and_braces_cutoff(self):
        installation = date(2026, 1, 1)
        self.assertFalse(_has_unfinished_treatment({'implant_installation': installation,
                                                  'implant_crown': installation}, self.reference))
        for days, expected in ((60, False), (61, True)):
            self.assertEqual(_has_unfinished_treatment({'braces_start': self.reference - timedelta(days=days)}, self.reference), expected)

    def test_ltv_recent_cohort_uses_pooled_rate(self):
        old = self.reference - timedelta(days=100)
        recent = self.reference - timedelta(days=10)
        histories = {'old': VisitHistory(old, self.reference, 2, 2, 1, 200, True),
                     'new': VisitHistory(recent, recent, 1, 1, 0, 100, True)}
        result = calculate_ltv({k: v.first_visit for k, v in histories.items()}, histories, self.reference)
        self.assertEqual(result['old'], (200, 365))
        self.assertEqual(result['new'], (100, 365))

    def test_ltv_without_eligible_cohorts_is_zero(self):
        first = self.reference - timedelta(days=29)
        history = VisitHistory(first, first, 1, 1, 0, 100, True)
        self.assertEqual(calculate_ltv({'a': first}, {'a': history}, self.reference)['a'], (100, 0))
