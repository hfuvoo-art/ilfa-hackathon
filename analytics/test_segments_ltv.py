"""Проверки RFM, бизнес-приоритетов и LTV без реальных данных пациентов."""

import unittest
from datetime import date
from math import isclose

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from analytics.demo_data import create_demo_db
from analytics.ltv import VisitHistory, calculate_ltv
from analytics.segments import (
    Patient,
    _business_segment,
    _has_unfinished_treatment,
    _rfm_scores,
    compute_segments,
)


class RFMSegmentTests(unittest.TestCase):
    def test_tied_values_have_identical_scores(self):
        values = [10, 10, 10, 20, 20, 40, 100]
        scores = _rfm_scores(values)
        self.assertEqual(len(scores), len(values))
        self.assertTrue(all(1 <= value <= 3 for value in scores))
        self.assertEqual(len(set(scores[:3])), 1)
        self.assertEqual(scores[3], scores[4])
        self.assertTrue(scores[0] <= scores[3] <= scores[-1])

    def test_recency_score_prefers_recent_visits(self):
        values = [2, 20, 200]
        scores = _rfm_scores(values, lower_is_better=True)
        self.assertEqual(scores, [3, 2, 1])

    def test_missing_rfm_value_is_neutral(self):
        self.assertEqual(_rfm_scores([None, 5, 10]), [2, 1, 3])

    def test_unfinished_treatment_overrides_sleeping_and_one_visit(self):
        reference = date(2026, 9, 30)
        patient = Patient('synthetic-patient', date(2025, 10, 1), date(2025, 10, 1),
                          364, 1, 1, 100, False)
        events = {'synthetic-patient': {'implant_installation': date(2025, 10, 1)}}
        self.assertTrue(_has_unfinished_treatment(events['synthetic-patient'], reference))
        self.assertEqual(_business_segment(patient, 10000, set(), events, reference),
                         'Незавершённое лечение')

    def test_recent_patient_is_new_even_without_repeat(self):
        reference = date(2026, 9, 30)
        patient = Patient('synthetic-patient', date(2026, 9, 1), date(2026, 9, 1),
                          29, 1, 1, 100, False)
        self.assertEqual(_business_segment(patient, 10000, set(), {}, reference), 'Новые')


class LTVTests(unittest.TestCase):
    def test_historical_ltv_preserves_refunds_prediction_nonnegative(self):
        histories = {
            'a': VisitHistory(date(2025, 10, 1), date(2026, 1, 1), 2, 2, 1, 1000, True),
            'b': VisitHistory(date(2025, 10, 1), date(2026, 1, 1), 1, 0, 0, -20, True),
        }
        result = calculate_ltv({key: h.first_visit for key, h in histories.items()}, histories,
                               date(2026, 9, 30))
        self.assertEqual(result['a'][0], 1000)
        self.assertEqual(result['b'], (-20, 0))
        self.assertTrue(all(predicted >= 0 for _, predicted in result.values()))

    def test_same_repeat_rate_same_expected_visits(self):
        report_date = date(2026, 9, 30)
        # 2 платных повтора за 120 дней и 1 повтор за 60 дней — равная частота
        histories = {
            'a': VisitHistory(date(2026, 6, 2), report_date, 3, 3, 2, 300, True),
            'b': VisitHistory(date(2026, 8, 1), report_date, 2, 2, 1, 200, True),
        }
        results = calculate_ltv({key: h.first_visit for key, h in histories.items()},
                                histories, report_date)
        self.assertTrue(isclose(results['a'][1], results['b'][1], rel_tol=0.01))


class IntegrationTests(unittest.TestCase):
    def test_demo_writes_all_four_fields_and_is_repeatable(self):
        raw = create_demo_db()
        engine = create_engine('sqlite://', creator=lambda: raw, poolclass=StaticPool)
        try:
            first = compute_segments(engine)
            with engine.connect() as conn:
                rows = conn.execute(text('''
                    SELECT patient_id, segment, rfm, ltv_hist, ltv_pred
                    FROM patients ORDER BY patient_id
                ''')).all()
                total = conn.execute(text('SELECT SUM(total_sum) FROM visits')).scalar_one()
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row.segment and row.rfm and row.ltv_hist is not None
                                and row.ltv_pred is not None for row in rows))
            self.assertTrue(isclose(sum(row.ltv_hist for row in rows), total, abs_tol=.005))
            self.assertEqual(sum(row['n_patients'] for row in first.values()), 5)
            self.assertEqual(first, compute_segments(engine))
            with engine.connect() as conn:
                self.assertEqual(rows, conn.execute(text('''
                    SELECT patient_id, segment, rfm, ltv_hist, ltv_pred
                    FROM patients ORDER BY patient_id
                ''')).all())
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
