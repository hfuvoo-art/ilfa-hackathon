"""Проверка фигур Plotly и их исходных показателей на синтетической SQLite."""

import unittest
from datetime import date

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from analytics.charts import load_chart_data, render_charts, return_scenario
from analytics.charts.__main__ import DEMO_ASSUMPTIONS
from analytics.demo_data import create_demo_db
from analytics.metrics import pareto_metrics
from analytics.segments import compute_segments


class ChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://", creator=lambda: create_demo_db(extended=True), poolclass=StaticPool,
        )
        cls.addClassCleanup(cls.engine.dispose)
        cls.segment_summary = compute_segments(cls.engine)
        cls.data = load_chart_data(cls.engine)
        cls.figures = render_charts(cls.data)

    def test_segments_pareto_and_ltv(self):
        self.assertEqual(sum(self.figures["segments"].data[0].x), 13)
        self.assertEqual(sum(row["n_patients"] for row in self.segment_summary.values()), 13)
        self.assertEqual(sum(row["ltv_hist"] for row in self.data["segments"]), 42700)
        self.assertEqual(sum(row["revenue"] for row in self.segment_summary.values()), 42700)
        self.assertEqual(self.figures["pareto"].data[0].y[-1], 1.0)
        self.assertGreaterEqual(self.figures["pareto"].data[1].y[0], 0.8)
        self.assertEqual(len(self.figures["ltv"].data), 2)
        self.assertEqual(pareto_metrics([0, -100]), ([], [], None))

    def test_chart_loading_does_not_read_service_rows_for_ltv(self):
        statements = []

        def record_query(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())

        event.listen(self.engine, "before_cursor_execute", record_query)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", record_query)
        report = {key: self.data[key] for key in ("services", "transitions")}
        data = load_chart_data(self.engine, service_report=report)

        self.assertEqual(data["segments"], self.data["segments"])
        self.assertFalse(any("visit_items" in statement for statement in statements))

    def test_service_and_transition_figures_use_report_aggregates(self):
        self.assertEqual(sum(self.figures["services"].data[0].x), 42700)
        heatmap = self.figures["transitions"].data[0]
        self.assertEqual(sum(cell[0] for row in heatmap.customdata for cell in row),
                         sum(row["n_transitions"] for row in self.data["transitions"]))
        for row in heatmap.z:
            known = [value for value in row if value is not None]
            if known:
                self.assertAlmostEqual(sum(known), 1.0)

    def test_calendar_totals_and_zero_month(self):
        months = {month: (count, revenue) for month, count, revenue in self.data["monthly"]}
        self.assertEqual(months[date(2026, 1, 1)], (6, 12000))
        self.assertEqual(months[date(2026, 4, 1)], (0, 0))
        self.assertEqual(sum(self.figures["monthly"].data[0].y), 24)
        self.assertEqual(sum(self.figures["monthly"].data[1].y), 42700)
        self.assertEqual(sum(self.figures["weekday"].data[0].y), 24)
        self.assertEqual(sum(self.figures["weekday"].data[0].customdata), 42700)

    def test_retention_uses_full_observation_windows(self):
        rows = {(row["cohort"], row["window"]): row for row in self.data["retention"]}
        self.assertAlmostEqual(rows["2025-10", 30]["share"], 2 / 3)
        self.assertEqual(rows["2025-10", 60]["n_returned"], 3)
        self.assertEqual(rows["2026-01", 60]["n_returned"], 3)
        self.assertIsNone(rows["2026-07", 30]["share"])

    def test_campaign_uses_only_lift_over_baseline(self):
        rows = return_scenario(self.data["patients"], **DEMO_ASSUMPTIONS)
        self.assertEqual([row["n_patients"] for row in rows], [3, 1])
        self.assertAlmostEqual(sum(row["incremental_revenue"] for row in rows), 440)
        no_lift = return_scenario(self.data["patients"], **{**DEMO_ASSUMPTIONS, "campaign_rate": 0.1})
        self.assertEqual(sum(row["incremental_revenue"] for row in no_lift), 0.0)

    def test_figures_serialize_and_have_takeaways(self):
        self.assertEqual(len(self.figures), 8)
        for name, figure in self.figures.items():
            with self.subTest(chart=name):
                self.assertTrue(figure.layout.title.text)
                self.assertTrue(figure.layout.annotations[-1].text)
                self.assertIn("Plotly.newPlot", figure.to_html(full_html=False, include_plotlyjs=False))
