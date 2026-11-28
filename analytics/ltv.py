"""Историческая выручка и прогноз LTV по когортам первого визита."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import groupby
from math import fsum

from sqlalchemy import text
from sqlalchemy.engine import Connection


MIN_OBSERVATION_DAYS = 30
DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class VisitHistory:
    first_visit: date | None = None
    last_visit: date | None = None
    n_visits: int = 0
    n_paid_visits: int = 0
    n_paid_repeats: int = 0
    revenue: float = 0.0
    is_complete: bool = False


EMPTY_HISTORY = VisitHistory()


def as_date(value: date | str | None) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else value


def load_visit_history(connection: Connection) -> dict[str, VisitHistory]:
    """Собирает историю по строкам визитов без чтения имён и комментариев."""
    rows = connection.execute(text("""
        SELECT patient_id, visit_date, has_services, total_sum
        FROM visits
        ORDER BY patient_id, visit_date NULLS LAST, visit_id
    """))
    histories = {}
    for patient_id, group in groupby(rows, key=lambda row: row.patient_id):
        visits = list(group)
        dates = [as_date(row.visit_date) for row in visits if row.visit_date is not None]
        paid = [bool(row.has_services and row.total_sum is not None and row.total_sum > 0) for row in visits]
        histories[patient_id] = VisitHistory(
            first_visit=dates[0] if dates else None,
            last_visit=dates[-1] if dates else None,
            n_visits=len(visits),
            n_paid_visits=sum(paid),
            n_paid_repeats=sum(paid[1:]),
            revenue=fsum(row.total_sum for row in visits if row.total_sum is not None),
            is_complete=len(dates) == len(visits) and all(
                row.total_sum is not None and (row.total_sum <= 0 or row.has_services is not None)
                for row in visits
            ),
        )
    return histories


def calculate_ltv(
    first_visits: dict[str, date | None],
    histories: dict[str, VisitHistory],
    report_date: date | None,
) -> dict[str, tuple[float, float]]:
    """Возвращает (исторический LTV, прогноз на 12 месяцев) для каждого пациента."""
    exposure = Counter()
    repeats = Counter()
    for patient_id in first_visits:
        history = histories.get(patient_id, EMPTY_HISTORY)
        if not history.is_complete or history.first_visit is None or report_date is None:
            continue
        observed_days = (report_date - history.first_visit).days
        if observed_days >= MIN_OBSERVATION_DAYS:
            cohort = history.first_visit.replace(day=1)
            exposure[cohort] += observed_days
            repeats[cohort] += history.n_paid_repeats

    # Учитываем дни наблюдения, включая дни пациентов без повторных визитов.
    # Для когорт без достаточного наблюдения используем общую частоту по доступным когортам.
    total_exposure = exposure.total()
    pooled_rate = repeats.total() / total_exposure if total_exposure else 0.0
    cohort_rates = {cohort: repeats[cohort] / days for cohort, days in exposure.items()}

    result = {}
    for patient_id, first_visit in first_visits.items():
        history = histories.get(patient_id, EMPTY_HISTORY)
        cohort_date = history.first_visit if history.is_complete else first_visit
        cohort = cohort_date.replace(day=1) if cohort_date is not None else None
        # Исторический LTV — фактическая выручка по контракту, включая возвраты.
        historical_ltv = history.revenue
        avg_check = max(0.0, historical_ltv) / history.n_paid_visits if history.n_paid_visits else 0.0
        expected_visits = cohort_rates.get(cohort, pooled_rate) * DAYS_PER_YEAR
        result[patient_id] = (historical_ltv, avg_check * expected_visits)
    return result


def summarize_ltv_by_segment(connection: Connection) -> list[dict]:
    """Возвращает число пациентов, суммы и средний LTV по сегментам."""
    rows = connection.execute(text("""
        SELECT segment, COUNT(*) AS n_patients,
               SUM(ltv_hist) AS ltv_hist, SUM(ltv_pred) AS ltv_pred,
               AVG(ltv_hist) AS avg_ltv_hist, AVG(ltv_pred) AS avg_ltv_pred
        FROM patients
        GROUP BY segment
        ORDER BY segment
    """)).mappings()
    return [dict(row) for row in rows]


def summarize_ltv(connection: Connection) -> dict[str, list[dict]]:
    """Возвращает число пациентов, суммы и средний LTV по сегменту и первой услуге."""
    by_segment = summarize_ltv_by_segment(connection)
    # Порядка строк услуг внутри визита в контракте нет. При равенстве берём название по алфавиту.
    by_first_service = connection.execute(text("""
        WITH eligible_services AS (
            SELECT v.patient_id, v.visit_date, v.visit_id, i.service_name
            FROM visits AS v
            JOIN visit_items AS i ON i.visit_id = v.visit_id
            WHERE (i.qty IS NULL OR i.qty > 0)
              AND (i.price IS NULL OR i.price >= 0)
              AND (i."sum" IS NULL OR i."sum" >= 0)
        ), ranked_services AS (
            SELECT e.patient_id, e.service_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY e.patient_id
                       ORDER BY e.visit_date, e.visit_id, e.service_name NULLS LAST
                   ) AS service_rank
            FROM eligible_services AS e
            WHERE NOT EXISTS (
                SELECT 1 FROM eligible_services AS undated
                WHERE undated.patient_id = e.patient_id AND undated.visit_date IS NULL
            )
        )
        SELECT s.service_name, COUNT(*) AS n_patients,
               SUM(p.ltv_hist) AS ltv_hist, SUM(p.ltv_pred) AS ltv_pred,
               AVG(p.ltv_hist) AS avg_ltv_hist, AVG(p.ltv_pred) AS avg_ltv_pred
        FROM patients AS p
        LEFT JOIN ranked_services AS s ON s.patient_id = p.patient_id AND s.service_rank = 1
        GROUP BY s.service_name
        ORDER BY s.service_name
    """)).mappings()
    return {
        "by_segment": by_segment,
        "by_first_service": [dict(row) for row in by_first_service],
    }
