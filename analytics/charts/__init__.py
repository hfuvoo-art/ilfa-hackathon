"""Набор интерактивных графиков по контракту данных."""

from types import SimpleNamespace

from sqlalchemy import text

from analytics.ltv import EMPTY_HISTORY, as_date, load_visit_history, summarize_ltv_by_segment
from analytics.metrics import pareto_metrics
from analytics.services import build_service_report

from .data import calendar_metrics, retention_metrics, return_scenario
from .figures import (
    ltv_chart,
    monthly_chart,
    pareto_chart,
    retention_chart,
    segment_chart,
    top_services_chart,
    transition_chart,
    weekday_chart,
)


def load_chart_data(engine, service_report=None):
    """Подготавливает агрегаты. Готовый отчёт по услугам можно передать повторно."""
    # Графики используют уже рассчитанные сегменты и LTV.
    if service_report is None:
        service_report = build_service_report(engine)
    with engine.connect() as connection:
        segments = summarize_ltv_by_segment(connection)
        patient_rows = connection.execute(text("""
            SELECT patient_id, segment, revenue, n_paid_visits FROM patients
        """)).all()
        visits = [
            SimpleNamespace(
                patient_id=row.patient_id, visit_date=as_date(row.visit_date),
                total_sum=row.total_sum, has_services=row.has_services,
            )
            for row in connection.execute(text("""
                SELECT patient_id, visit_date, total_sum, has_services FROM visits
            """))
        ]
        needs_history = any(row.revenue is None or row.n_paid_visits is None for row in patient_rows)
        histories = load_visit_history(connection) if needs_history else {}
        patients = []
        for row in patient_rows:
            history = histories.get(row.patient_id, EMPTY_HISTORY)
            patients.append(SimpleNamespace(
                segment=row.segment,
                revenue=row.revenue if row.revenue is not None else history.revenue,
                n_paid_visits=row.n_paid_visits if row.n_paid_visits is not None else history.n_paid_visits,
            ))

    monthly, weekday = calendar_metrics(visits)
    return {
        "segments": segments,
        "pareto": pareto_metrics(patient.revenue for patient in patients),
        "services": service_report["services"],
        "transitions": service_report["transitions"],
        "retention": retention_metrics(visits),
        "monthly": monthly,
        "weekday": weekday,
        "patients": patients,
    }


def render_charts(data):
    """Строит восемь фигур из подготовленного набора данных."""
    return {
        "segments": segment_chart(data["segments"]),
        "pareto": pareto_chart(*data["pareto"]),
        "ltv": ltv_chart(data["segments"]),
        "services": top_services_chart(data["services"]),
        "retention": retention_chart(data["retention"]),
        "transitions": transition_chart(data["transitions"]),
        "monthly": monthly_chart(data["monthly"]),
        "weekday": weekday_chart(data["weekday"]),
    }


def build_charts(engine, service_report=None):
    """Возвращает готовые фигуры Plotly для встраивания в интерфейс."""
    return render_charts(load_chart_data(engine, service_report))
