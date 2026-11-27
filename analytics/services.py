"""Выручка, скидки и переходы между категориями услуг."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise
from math import fsum, isclose

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import SQLAlchemyError

CATEGORIES = {
    "Терапия", "Гигиена", "Хирургия", "Имплантация", "Ортопедия", "Ортодонтия",
    "Детская", "Диагностика", "Консультация", "Прочее",
}
TRANSITION_FIELDS = ("from_category", "to_category", "n_transitions", "n_patients", "transition_share")


@dataclass(frozen=True)
class ServiceLine:
    visit_id: int
    service_name: str | None
    category: str | None
    qty: float | None
    price: float | None
    amount: float | None
    discount: float | None

    @property
    def is_adjustment(self) -> bool:
        return any(value is not None and value < 0 for value in (self.qty, self.price, self.amount))

    @property
    def is_service(self) -> bool:
        return not self.is_adjustment and self.qty != 0


def _financial_summary(lines: list[ServiceLine], total_revenue: float) -> dict:
    revenue = fsum(line.amount for line in lines if line.amount is not None)
    services = [line for line in lines if line.is_service]
    adjustments = [line for line in lines if line.is_adjustment]
    discounts = [
        line.discount
        for line in services
        if line.qty is not None and line.price is not None and line.amount is not None
        and line.discount is not None and line.discount >= 0
    ]
    visits = {line.visit_id for line in lines}
    return {
        "n_rows": len(lines),
        "n_visits": len(visits),
        "n_service_rows": len(services),
        "qty": fsum(line.qty for line in services if line.qty is not None),
        "n_unknown_qty": sum(line.qty is None for line in services),
        "revenue": revenue,
        "revenue_share": revenue / total_revenue if total_revenue != 0 else None,
        "avg_revenue_per_visit": revenue / len(visits) if visits else None,
        "discount": fsum(discounts),
        "n_discounted_rows": sum(value > 0 for value in discounts),
        "n_unknown_discount": len(services) - len(discounts),
        "n_adjustment_rows": len(adjustments),
        "negative_amount": fsum(-line.amount for line in adjustments if line.amount is not None and line.amount < 0),
    }


def _primary_category(lines: list[ServiceLine]) -> str | None:
    amounts = defaultdict(list)
    for line in lines:
        amounts[line.category].append(line.amount or 0.0)
    if not amounts:
        return None
    # При равной выручке выбираем известную категорию, затем название по алфавиту.
    return min(amounts, key=lambda category: (-fsum(amounts[category]), category is None, category or ""))


def _transitions(
    visits_by_patient: dict[str, list[Row]], primary_categories: dict[int, str | None],
) -> tuple[list[dict], dict[str, int]]:
    pair_counts = Counter()
    patients_by_pair = defaultdict(set)
    outgoing = Counter()
    candidate_pairs = 0
    n_undated_histories = 0
    for patient_id, visits in visits_by_patient.items():
        if any(visit.visit_date is None for visit in visits):
            n_undated_histories += 1
            continue
        for previous, following in pairwise(visits):
            candidate_pairs += 1
            source = primary_categories.get(previous.visit_id)
            target = primary_categories.get(following.visit_id)
            if source is None or target is None:
                continue
            pair = (source, target)
            pair_counts[pair] += 1
            patients_by_pair[pair].add(patient_id)
            outgoing[source] += 1

    rows = [
        {
            "from_category": source,
            "to_category": target,
            "n_transitions": count,
            "n_patients": len(patients_by_pair[source, target]),
            "transition_share": count / outgoing[source],
        }
        for (source, target), count in sorted(pair_counts.items())
    ]
    return rows, {
        "candidate_pairs": candidate_pairs,
        "skipped_pairs": candidate_pairs - pair_counts.total(),
        "n_undated_histories": n_undated_histories,
    }


def _first_category(visits: list[Row], services_by_visit: dict[int, list[ServiceLine]]) -> str | None:
    service_visits = [visit for visit in visits if services_by_visit.get(visit.visit_id)]
    if not service_visits or any(visit.visit_date is None for visit in service_visits):
        return None
    first_lines = services_by_visit[service_visits[0].visit_id]
    # Порядок строк внутри визита отсутствует. Выбираем одно название по алфавиту.
    return min(first_lines, key=lambda line: (
        line.service_name is None, line.service_name or "", line.category is None, line.category or "",
    )).category


def build_service_report(engine: Engine) -> dict:
    """Читает таблицы контракта и возвращает сводки без идентификаторов пациентов."""
    if engine.dialect.name == "postgresql":
        engine = engine.execution_options(isolation_level="REPEATABLE READ")
    with engine.begin() as connection:
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
        visits = connection.execute(text("""
            SELECT visit_id, patient_id, visit_date, total_sum
            FROM visits
            ORDER BY visit_date NULLS LAST, visit_id
        """)).all()
        source_lines = connection.execute(text("""
            SELECT visit_id, service_name, category, qty, price, "sum" AS amount, discount
            FROM visit_items
        """))
        lines = [
            ServiceLine(
                row.visit_id, row.service_name, row.category if row.category in CATEGORIES else None,
                row.qty, row.price, row.amount, row.discount,
            )
            for row in source_lines
        ]
        patients = connection.execute(text("SELECT patient_id, ltv_hist FROM patients")).all()

    total_revenue = fsum(line.amount for line in lines if line.amount is not None)
    by_category = defaultdict(list)
    by_service = defaultdict(list)
    items_by_visit = defaultdict(list)
    services_by_visit = defaultdict(list)
    for line in lines:
        by_category[line.category].append(line)
        by_service[line.category, line.service_name].append(line)
        items_by_visit[line.visit_id].append(line)
        if line.is_service:
            services_by_visit[line.visit_id].append(line)

    categories = [
        {"category": category, **_financial_summary(group, total_revenue)}
        for category, group in by_category.items()
    ]
    categories.sort(key=lambda row: (-row["revenue"], row["category"] or ""))
    services = [
        {"category": category, "service_name": service_name, **_financial_summary(group, total_revenue)}
        for (category, service_name), group in by_service.items()
    ]
    services.sort(key=lambda row: (-row["revenue"], row["category"] or "", row["service_name"] or ""))

    visits_by_patient = defaultdict(list)
    for visit in visits:
        if visit.patient_id is not None:
            visits_by_patient[visit.patient_id].append(visit)
    primary_categories = {
        visit_id: _primary_category(group) for visit_id, group in services_by_visit.items()
    }
    transitions, transition_coverage = _transitions(visits_by_patient, primary_categories)

    ltv_by_category = defaultdict(list)
    for patient in patients:
        category = _first_category(visits_by_patient.get(patient.patient_id, []), services_by_visit)
        ltv_by_category[category].append(patient.ltv_hist)
    first_category_ltv = []
    for category, values in sorted(ltv_by_category.items(), key=lambda item: item[0] or ""):
        known = [value for value in values if value is not None]
        total_ltv = fsum(known) if known else None
        first_category_ltv.append({
            "category": category,
            "n_patients": len(values),
            "n_with_ltv": len(known),
            "ltv_hist": total_ltv,
            "avg_ltv_hist": total_ltv / len(known) if known else None,
        })

    visit_revenue = fsum(visit.total_sum for visit in visits if visit.total_sum is not None)
    category_revenue = fsum(row["revenue"] for row in categories)
    visit_ids = {visit.visit_id for visit in visits}
    return {
        "totals": _financial_summary(lines, total_revenue),
        "reconciliation": {
            "visit_revenue": visit_revenue,
            "item_revenue": total_revenue,
            "category_revenue": category_revenue,
            "items_minus_visits": total_revenue - visit_revenue,
            "categories_match_items": isclose(category_revenue, total_revenue, rel_tol=0, abs_tol=0.005),
            "items_match_visits": isclose(total_revenue, visit_revenue, rel_tol=0, abs_tol=0.005),
            "n_visit_total_mismatches": sum(
                not isclose(
                    visit.total_sum,
                    fsum(line.amount for line in items_by_visit.get(visit.visit_id, []) if line.amount is not None),
                    rel_tol=0, abs_tol=0.005,
                )
                for visit in visits if visit.total_sum is not None
            ),
            "n_orphan_items": sum(line.visit_id not in visit_ids for line in lines),
            "n_missing_amounts": sum(line.amount is None for line in lines),
            "n_missing_visit_totals": sum(visit.total_sum is None for visit in visits),
        },
        "categories": categories,
        "services": services,
        "other": {
            "summary": next((row for row in categories if row["category"] == "Прочее"), None),
            "services": [row for row in services if row["category"] == "Прочее"],
        },
        "ltv_by_first_category": first_category_ltv,
        "transitions": transitions,
        "transition_coverage": transition_coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transitions-csv", action="store_true", help="Вывести только матрицу переходов в CSV.")
    args = parser.parse_args()
    engine = None
    try:
        engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///data/ilfa.db"))
        report = build_service_report(engine)
    except SQLAlchemyError as exc:
        print(f"Ошибка доступа к базе ({type(exc).__name__}). Проверьте DATABASE_URL и таблицы ETL.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    if args.transitions_csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=TRANSITION_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["transitions"])
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
