"""Календарные показатели, удержание и сценарий возврата пациентов."""

from collections import Counter, defaultdict
from datetime import timedelta
from math import fsum, isfinite


RETENTION_WINDOWS = (30, 60, 90)
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
RETURN_SEGMENTS = ("Пропал после 1 визита", "Спящие")


def calendar_metrics(visits):
    """Визиты и выручка по месяцам и дням недели. Даты берём из visits."""
    monthly = defaultdict(list)
    weekly = defaultdict(list)
    for visit in visits:
        if visit.visit_date is not None:
            monthly[visit.visit_date.replace(day=1)].append(visit.total_sum or 0)
            weekly[visit.visit_date.weekday()].append(visit.total_sum or 0)

    month_rows = []
    if monthly:
        month, last = min(monthly), max(monthly)
        while month <= last:
            amounts = monthly.get(month, [])
            month_rows.append((month, len(amounts), fsum(amounts)))
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    weekday_rows = [(day, len(weekly[index]), fsum(weekly[index])) for index, day in enumerate(WEEKDAYS)]
    return month_rows, weekday_rows


def retention_metrics(visits, windows=RETENTION_WINDOWS):
    """Доля пациентов с повторным визитом с услугами в фиксированное окно."""
    report_date = max((visit.visit_date for visit in visits if visit.visit_date is not None), default=None)
    if report_date is None:
        return []

    by_patient = defaultdict(list)
    for visit in visits:
        if visit.patient_id is not None:
            by_patient[visit.patient_id].append(visit)
    cohorts = defaultdict(list)
    for history in by_patient.values():
        if any(visit.visit_date is None for visit in history):
            continue
        first = min(visit.visit_date for visit in history)
        days_until_repeat = min(
            ((visit.visit_date - first).days for visit in history
             if visit.has_services and visit.visit_date > first),
            default=None,
        )
        cohorts[first.replace(day=1)].append(((report_date - first).days, days_until_repeat))

    result = []
    for month, cohort in sorted(cohorts.items()):
        for window in windows:
            complete = all(observed >= window for observed, _ in cohort)
            returned = sum(delay is not None and delay <= window for _, delay in cohort) if complete else None
            result.append({
                "cohort": month.isoformat()[:7],
                "window": window,
                "n_patients": len(cohort),
                "n_returned": returned,
                "share": returned / len(cohort) if returned is not None else None,
            })
    return result


def return_scenario(patients, *, contact_share, baseline_rate, campaign_rate, visits_per_return=1):
    """Сценарная дополнительная выручка после вычета органического возврата."""
    if any(not 0 <= value <= 1 for value in (contact_share, baseline_rate, campaign_rate)):
        raise ValueError("Охват и доли возврата должны лежать от 0 до 1.")
    if not isfinite(visits_per_return) or visits_per_return < 0:
        raise ValueError("Число визитов должно быть конечным и неотрицательным.")
    counts = Counter()
    revenue = defaultdict(list)
    paid_visits = Counter()
    for patient in patients:
        if patient.segment in RETURN_SEGMENTS:
            counts[patient.segment] += 1
            revenue[patient.segment].append(patient.revenue or 0.0)
            paid_visits[patient.segment] += patient.n_paid_visits or 0

    rows = []
    for segment in RETURN_SEGMENTS:
        count = counts[segment]
        check = max(0.0, fsum(revenue[segment]) / paid_visits[segment]) if paid_visits[segment] else None
        contacted = count * contact_share
        incremental_returns = contacted * (campaign_rate - baseline_rate)
        rows.append({
            "segment": segment,
            "n_patients": count,
            "avg_check": check,
            "incremental_returns": incremental_returns,
            "incremental_revenue": incremental_returns * visits_per_return * check if check is not None else None,
        })
    return rows
