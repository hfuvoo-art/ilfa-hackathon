from collections import Counter, defaultdict
from datetime import date
from math import fsum


def build_patients(visits, items, report_date=None):
    if not visits:
        return []

    report_date = report_date or max(date.fromisoformat(str(row["visit_date"])) for row in visits)
    by_patient = defaultdict(list)
    patient_by_visit = {}
    for visit in visits:
        patient_id = visit["patient_id"]
        by_patient[patient_id].append(visit)
        patient_by_visit[visit["visit_id"]] = patient_id

    categories = defaultdict(set)
    doctors = defaultdict(Counter)
    for item in items:
        patient_id = patient_by_visit[item["visit_id"]]
        categories[patient_id].add(item["category"])
        if item["doctor"]:
            doctors[patient_id][item["doctor"]] += 1

    patients = []
    for patient_id, history in by_patient.items():
        history.sort(key=lambda row: (str(row["visit_date"]), row["visit_id"]))
        first, last = history[0], history[-1]
        first_visit = date.fromisoformat(str(first["visit_date"]))
        last_visit = date.fromisoformat(str(last["visit_date"]))
        revenue = fsum(visit["total_sum"] for visit in history)
        paid = sum(visit["has_services"] and visit["total_sum"] > 0 for visit in history)
        genders = {visit["gender"] for visit in history if visit["gender"] != "unknown"}
        doctor_counts = doctors[patient_id]
        main_doctor = min(doctor_counts, key=lambda name: (-doctor_counts[name], name), default=None)
        patients.append({
            "patient_id": patient_id,
            "last_name": last["last_name"],
            "first_name": last["first_name"],
            "gender": next(iter(genders)) if len(genders) == 1 else "unknown",
            "first_visit": first_visit,
            "last_visit": last_visit,
            "n_visits": len(history),
            "n_paid_visits": paid,
            "revenue": revenue,
            "avg_check": revenue / paid if paid else None,
            "days_since_last": (report_date - last_visit).days,
            "categories": ",".join(sorted(categories[patient_id])),
            "main_doctor": main_doctor,
            "is_child": "Детская" in categories[patient_id],
        })
    return patients
