"""RFM, бизнес-сегментация и LTV по таблицам контракта данных."""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby
from math import fsum, isclose

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import SQLAlchemyError

from analytics.ltv import EMPTY_HISTORY, VisitHistory, as_date, calculate_ltv, load_visit_history


@dataclass(frozen=True)
class Patient:
    patient_id: str
    first_visit: date | None
    last_visit: date | None
    days_since_last: int | None
    n_visits: int
    n_paid_visits: int
    revenue: float
    is_child: bool

    @classmethod
    def from_row(cls, row: RowMapping, history: VisitHistory, report_date: date | None) -> Patient:
        first_visit = as_date(row.first_visit) or history.first_visit
        last_visit = as_date(row.last_visit) or history.last_visit
        recency = row.days_since_last
        if recency is None and report_date is not None and last_visit is not None:
            recency = (report_date - last_visit).days
        return cls(
            row.patient_id,
            first_visit,
            last_visit,
            recency,
            history.n_visits if row.n_visits is None else row.n_visits,
            history.n_paid_visits if row.n_paid_visits is None else row.n_paid_visits,
            history.revenue if row.revenue is None else row.revenue,
            bool(row.is_child),
        )


def _rfm_scores(values: list[int | float | None], *, lower_is_better: bool = False) -> list[int]:
    """Границы третей по рангу. Одинаковые значения получают средний ранг группы."""
    known = [(index, value) for index, value in enumerate(values) if value is not None]
    ordered = sorted(known, key=lambda item: item[1], reverse=lower_is_better)
    scores = [2] * len(values)
    start = 0
    for _, tied in groupby(ordered, key=lambda item: item[1]):
        group = list(tied)
        end = start + len(group)
        score = 1 + 3 * (start + end) // (2 * len(ordered))
        for index, _ in group:
            scores[index] = score
        start = end
    return scores


def _treatment_event(service_name: str, category: str, is_chain_start: bool) -> str | None:
    """Распознаём только этапы, для которых в плане описано продолжение."""
    name = service_name.casefold()
    if "коронк" in name and "имплант" in name and category in {"Имплантация", "Ортопедия"}:
        return "implant_crown"
    if category == "Ортодонтия" and "коррекц" in name and (
        "брекет" in name or re.search(r"\bортодонтическ\w*\s+коррекц", name)
    ):
        return "braces_adjustment"
    if not is_chain_start:
        return None
    if "имплант" in name and "миниимплант" not in name:
        if category == "Имплантация" and re.search(r"\bустановк\w*\s+(?:дентальн\w*\s+)?имплант", name):
            return "implant_installation"
        if category in {"Имплантация", "Диагностика", "Консультация"} and re.search(
            r"\bкт\b|томограф|консультац", name
        ):
            return "implant_planning"
    if category == "Ортодонтия" and re.search(
        r"^\s*брекет[\s-]*систем|(?:установк|фиксаци)\w*\s+брекет", name
    ):
        return "braces_start"
    return None


def _treatment_dates(connection: Connection) -> dict[str, dict[str, date]]:
    dates: dict[str, dict[str, date]] = defaultdict(dict)
    for row in connection.execute(text("""
        SELECT v.patient_id, v.visit_date, i.service_name, s.category, s.is_chain_start
        FROM visits AS v
        JOIN visit_items AS i ON i.visit_id = v.visit_id
        JOIN services AS s ON s.service_name = i.service_name
        WHERE v.visit_date IS NOT NULL
          AND (s.is_chain_start OR s.category IN ('Имплантация', 'Ортопедия', 'Ортодонтия'))
        ORDER BY v.visit_date
    """)):
        event = _treatment_event(row.service_name, row.category, row.is_chain_start)
        if event:
            dates[row.patient_id][event] = as_date(row.visit_date)
    return dates


def _has_unfinished_treatment(events: dict[str, date], report_date: date) -> bool:
    installation = events.get("implant_installation")
    crown = events.get("implant_crown")
    planning = events.get("implant_planning")
    braces = events.get("braces_start")
    adjustment = events.get("braces_adjustment")

    # События одного дня считаем связанными, поскольку времени визита в контракте нет.
    return (
        (installation is not None and (crown is None or crown < installation))
        or (planning is not None and (installation is None or installation < planning))
        or (
            braces is not None and (report_date - braces).days > 60
            and (adjustment is None or adjustment < braces)
        )
    )


def _business_segment(
    patient: Patient,
    top_revenue: float,
    hygiene_only: set[str],
    treatment_dates: dict[str, dict[str, date]],
    report_date: date | None,
) -> str:
    recency = patient.days_since_last
    if patient.last_visit is not None and recency is not None:
        report_date = patient.last_visit + timedelta(days=recency)
    if patient.revenue >= top_revenue and patient.n_paid_visits >= 3 and recency is not None and recency <= 180:
        return "Ценные лояльные"
    if report_date is not None and patient.first_visit is not None and (report_date - patient.first_visit).days <= 60:
        return "Новые"
    if report_date is not None and _has_unfinished_treatment(treatment_dates.get(patient.patient_id, {}), report_date):
        return "Незавершённое лечение"
    if patient.n_visits == 1 and recency is not None and recency > 90:
        return "Пропал после 1 визита"
    if patient.patient_id in hygiene_only:
        return "Только гигиена"
    if patient.n_paid_visits >= 2 and recency is not None and recency > 180:
        return "Спящие"
    if patient.is_child:
        return "Дети и семьи"
    return "Активные"


def compute_segments(engine: Engine) -> dict[str, dict[str, int | float]]:
    """Записывает segment, rfm и LTV. Возвращает прежнюю сводку по сегментам."""
    if engine.dialect.name == "postgresql":
        engine = engine.execution_options(isolation_level="REPEATABLE READ")

    with engine.begin() as connection:
        # В SQLite начинаем транзакцию до чтения, чтобы ETL не обновил срез между запросами.
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")

        patient_rows = connection.execute(text("""
            SELECT patient_id, first_visit, last_visit, days_since_last, n_visits, n_paid_visits,
                   revenue, is_child
            FROM patients
        """)).mappings().all()
        totals = connection.execute(text("""
            SELECT COALESCE(SUM(total_sum), 0) AS revenue, MAX(visit_date) AS last_visit
            FROM visits
        """)).one()
        total_revenue = totals.revenue
        report_date = as_date(totals.last_visit)
        histories = load_visit_history(connection)
        patients = [
            Patient.from_row(row, histories.get(row.patient_id, EMPTY_HISTORY), report_date)
            for row in patient_rows
        ]
        if set(histories) - {patient.patient_id for patient in patients}:
            raise ValueError("В visits есть записи без пациента в patients. Проверьте выгрузку ETL.")
        # Общая сумма не обнаруживает ошибки, компенсирующиеся между пациентами.
        for patient in patients:
            history = histories.get(patient.patient_id, EMPTY_HISTORY)
            if (not isclose(patient.revenue, history.revenue, rel_tol=0, abs_tol=0.005)
                    or patient.n_visits != history.n_visits
                    or patient.n_paid_visits != history.n_paid_visits):
                raise ValueError("Показатели пациента расходятся с visits. Пересоберите витрину ETL.")
        if not isclose(fsum(patient.revenue for patient in patients), total_revenue, rel_tol=0, abs_tol=0.005):
            raise ValueError("Выручка в patients расходится с visits. Проверьте выгрузку ETL.")
        if not patients:
            return {}

        # Бесплатные услуги не влияют на сегмент. Без строк платного визита данных недостаточно.
        hygiene_only = set(connection.execute(text("""
            SELECT v.patient_id
            FROM visits AS v
            LEFT JOIN visit_items AS i ON i.visit_id = v.visit_id AND i."sum" > 0
            WHERE v.has_services AND v.total_sum > 0
            GROUP BY v.patient_id
            HAVING MIN(CASE WHEN i.category = 'Гигиена' THEN 1 ELSE 0 END) = 1
        """)).scalars())
        treatment_dates = _treatment_dates(connection)

        revenues = [patient.revenue for patient in patients]
        recency_scores = _rfm_scores([patient.days_since_last for patient in patients], lower_is_better=True)
        frequency_scores = _rfm_scores([patient.n_paid_visits for patient in patients])
        monetary_scores = _rfm_scores(revenues)
        # Берём верхнюю пятую часть с округлением вверх и сохраняем ничьи на границе.
        top_count = (len(patients) + 4) // 5
        top_revenue = sorted(revenues, reverse=True)[top_count - 1]

        ltv = calculate_ltv({p.patient_id: p.first_visit for p in patients}, histories, report_date)
        updates = []
        for patient, r, f, m in zip(patients, recency_scores, frequency_scores, monetary_scores, strict=True):
            ltv_hist, ltv_pred = ltv[patient.patient_id]
            updates.append({
                "patient_id": patient.patient_id,
                "segment": _business_segment(patient, top_revenue, hygiene_only, treatment_dates, report_date),
                "rfm": f"R{r}F{f}M{m}",
                "ltv_hist": ltv_hist,
                "ltv_pred": ltv_pred,
            })
        connection.execute(text("""
            UPDATE patients
            SET segment = :segment, rfm = :rfm, ltv_hist = :ltv_hist, ltv_pred = :ltv_pred
            WHERE patient_id = :patient_id
        """), updates)

        rows = connection.execute(text("""
            WITH missing_revenue AS (
                SELECT v.patient_id, SUM(v.total_sum) AS revenue
                FROM visits AS v
                JOIN patients AS p ON p.patient_id = v.patient_id
                WHERE p.revenue IS NULL
                GROUP BY v.patient_id
            )
            SELECT p.segment, COUNT(*) AS n_patients, COUNT(p.rfm) AS n_rfm,
                   COUNT(CASE WHEN p.ltv_hist IS NOT NULL AND p.ltv_pred >= 0 THEN 1 END) AS n_valid_ltv,
                   SUM(p.ltv_hist) AS historical_ltv,
                   SUM(COALESCE(p.revenue, m.revenue, 0)) AS revenue
            FROM patients AS p
            LEFT JOIN missing_revenue AS m ON m.patient_id = p.patient_id
            GROUP BY p.segment
            ORDER BY p.segment
        """)).all()
        expected_counts = Counter(update["segment"] for update in updates)
        actual_counts = {row.segment: row.n_patients for row in rows}
        if actual_counts != expected_counts or any(row.n_rfm != row.n_patients for row in rows):
            raise ValueError("Проверка не пройдена. У каждого пациента должны быть один сегмент и код RFM.")
        # Исторический LTV и выручка одинаково учитывают возвраты.
        if not isclose(fsum(row.revenue for row in rows), total_revenue, rel_tol=0, abs_tol=0.005):
            raise ValueError("Выручка по сегментам расходится с общей выручкой.")
        if any(row.n_valid_ltv != row.n_patients for row in rows) or not isclose(
            fsum(row.historical_ltv or 0.0 for row in rows), total_revenue, rel_tol=0, abs_tol=0.005
        ):
            raise ValueError("Исторический LTV не сходится с выручкой или в LTV есть пропуски.")
        return {row.segment: {"n_patients": row.n_patients, "revenue": row.revenue} for row in rows}


def main() -> int:
    engine = None
    try:
        engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///data/ilfa.db"))
        summary = compute_segments(engine)
    except SQLAlchemyError as exc:
        print(
            f"Ошибка доступа к базе ({type(exc).__name__}). Проверьте DATABASE_URL и таблицы ETL.",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(f"Ошибка сегментации: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    print(f'Пациентов обработано: {sum(row["n_patients"] for row in summary.values())}')
    for segment, row in summary.items():
        print(f'{segment} — {row["n_patients"]} чел., {row["revenue"]:.2f} ₽')
    print(f'Общая выручка: {fsum(row["revenue"] for row in summary.values()):.2f} ₽')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
