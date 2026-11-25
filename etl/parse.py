from datetime import datetime
from pathlib import Path

import xlrd

from .ids import make_patient_id


def normalize_text(value):
    return " ".join(str(value).split())


def parse_file(path):
    path = Path(path)
    workbook = xlrd.open_workbook(str(path))
    sheet = workbook.sheet_by_index(0)

    header = {}
    items = []
    in_services = False

    for row_index in range(sheet.nrows):
        label = normalize_text(sheet.cell_value(row_index, 0))

        if label == "Наименование":
            in_services = True
            continue
        if not in_services:
            if label:
                header[label] = sheet.cell_value(row_index, 1)
            continue

        _, doctor, qty, price, amount = sheet.row_values(
            row_index, start_colx=0, end_colx=5
        )
        doctor = normalize_text(doctor).title()

        if not label:
            has_numbers = all(
                isinstance(value, (int, float))
                for value in (qty, price, amount)
            )
            if not (doctor and has_numbers and qty > 0):
                continue
        qty, price, amount = float(qty), float(price), float(amount)
        items.append({
            "service_name": label,
            "category": None,
            "doctor": doctor,
            "qty": qty,
            "price": price,
            "sum": amount,
            "discount": max(price * qty - amount, 0.0),
        })

    visit_id = int(header["№"])
    last_name = normalize_text(header["Фамилия"])
    first_name = normalize_text(header["Имя"])
    gender = normalize_text(header.get("Пол", ""))

    visit = {
        "visit_id": visit_id,
        "visit_date": datetime.strptime(
            normalize_text(header["Дата визита"]), "%d.%m.%Y"
        ).date(),
        "patient_id": make_patient_id(last_name, first_name),
        "last_name": last_name,
        "first_name": first_name,
        "gender": {"Жен": "F", "Муж": "M"}.get(gender, "unknown"),
        "author": normalize_text(header.get("Автор", "")),
        "comment": normalize_text(header.get("Комментарий", "")),
        "total_sum": sum(item["sum"] for item in items),
        "has_services": bool(items),
        "source_file": path.name,
    }

    for item in items:
        item["visit_id"] = visit_id

    return visit, items
