"""Фейковые данные строго по shared/DATA_CONTRACT.md.

Нужны, пока data-инженер, аналитик и ML-разработчик не отдали настоящие таблицы.
Когда настоящая база готова, приложение переключается на неё само (см. repository.py),
код экранов и API менять не нужно.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

import pandas as pd

SEED = 42
REPORT_DATE = date(2026, 9, 30)
START_DATE = date(2025, 10, 1)

DOCTORS = [
    "Иванова Анна Сергеевна", "Петров Олег Игоревич", "Сидорова Мария Павловна",
    "Кузнецов Артём Викторович", "Смирнова Елена Андреевна",
]
AUTHORS = ["Администратор 1", "Администратор 2", "Администратор 3"]

# (название, категория, цена, follow_up_days, is_chain_start)
SERVICES = [
    ("Профессиональная гигиена полости рта", "Гигиена", 6500, 180, False),
    ("Лечение кариеса средней степени", "Терапия", 9000, 365, False),
    ("Лечение каналов 2 канала", "Терапия", 18000, 365, True),
    ("Компьютерная томография (КТ) 2х челюстей", "Диагностика", 5500, None, True),
    ("Консультация стоматолога", "Консультация", 1500, None, False),
    ("Установка имплантата Dentium", "Имплантация", 55000, 365, True),
    ("Коронка на имплантат цирконий", "Имплантация", 60000, 365, False),
    ("Керамическая коронка E.max", "Ортопедия", 45000, 365, False),
    ("Брекет-система на 1 зубной ряд", "Ортодонтия", 120000, 45, True),
    ("Ортодонтическая коррекция (плановое посещение)", "Ортодонтия", 7000, 45, False),
    ("Лечение кариеса молочного зуба", "Детская", 6000, 180, False),
    ("Удаление зуба сложное", "Хирургия", 9000, None, False),
]

COMMENTS = [
    "", "", "гигиена", "кормящая мама, переживает за безболезненность",
    "тревожная, боится уколов", "презентация имплантации, думает",
    "дорого, спрашивала про рассрочку", "с ребенком", "корр", "лечение кариеса",
]

# Теги заданы вручную для фейковых комментариев. Настоящие теги строит offers/.
COMMENT_TAGS = {
    "кормящая мама, переживает за безболезненность": ["parent", "pregnant_or_nursing", "anxious"],
    "тревожная, боится уколов": ["anxious"],
    "презентация имплантации, думает": ["complex_case", "thinking"],
    "дорого, спрашивала про рассрочку": ["price_sensitive"],
    "с ребенком": ["parent"],
}

TRIGGERS = {
    "implant_control": ("Прошёл почти год после имплантации", "Контрольный осмотр и гигиена", "reliability"),
    "hygiene_due": ("Полгода с последней гигиены", "Профессиональная гигиена", "care"),
    "hygiene_only": ("Приходил только на гигиену", "Бережная диагностика кариеса", "light"),
    "unfinished_implant": ("Лечение по имплантации не завершено", "Продолжить лечение, гарантия", "reliability"),
    "unfinished_ortho": ("Давно не было коррекции брекетов", "Вернуться на коррекцию", "care"),
    "lost_after_first": ("Был один раз и не вернулся", "Приглашение на осмотр", "care"),
    "sleeping_valuable": ("Постоянный пациент давно не был", "Приглашение к своему врачу", "care"),
    "child_checkup": ("Пора на осмотр ребёнка", "Осмотр ребёнка", "calm"),
}

TEXTS = {
    "care": "{name}, здравствуйте! Это клиника «Ильфа». {reason_lc} — будем рады видеть вас снова. Подобрать удобное время?",
    "calm": "{name}, здравствуйте! Клиника «Ильфа» на связи. {reason_lc}. Всё пройдёт спокойно и без боли, врач заранее всё объяснит. Записать вас?",
    "reliability": "{name}, здравствуйте! Это «Ильфа». {reason_lc}. Контрольный визит помогает сохранить результат лечения и гарантию. Подберём время?",
    "light": "{name}, привет от «Ильфы»! {reason_lc}. Заглянете на короткий осмотр? Это быстро.",
}


def patient_id(last_name: str, first_name: str) -> str:
    """Временная копия функции из контракта. Когда etl/ids.py появится — импортировать оттуда."""
    key = f"{last_name.strip().lower()}|{first_name.strip().lower()}".replace("ё", "е")
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def build(n_patients: int = 30) -> dict[str, pd.DataFrame]:
    rnd = random.Random(SEED)
    services = pd.DataFrame(SERVICES, columns=["service_name", "category", "price", "follow_up_days", "is_chain_start"])
    services = services.drop(columns="price")  # цены нет в контракте таблицы services

    visits, items, patients = [], [], []
    visit_id = 100000
    for i in range(1, n_patients + 1):
        last, first = f"Фамилия {i}", f"Имя {i}"
        pid = patient_id(last, first)
        gender = rnd.choice(["F", "M", "unknown"])
        n_vis = rnd.choice([1, 1, 2, 3, 4, 6, 8])
        dates = sorted(START_DATE + timedelta(days=rnd.randint(0, 364)) for _ in range(n_vis))
        for d in dates:
            visit_id += 1
            n_items = rnd.choice([0, 1, 1, 2, 3])
            vis_items = []
            for _ in range(n_items):
                name, cat, price, *_ = rnd.choice(SERVICES)
                qty = 1.0
                disc = rnd.choice([0, 0, 0, round(price * 0.1)])
                vis_items.append({
                    "visit_id": visit_id, "service_name": name, "category": cat,
                    "doctor": rnd.choice(DOCTORS), "qty": qty, "price": float(price),
                    "sum": float(price * qty - disc), "discount": float(disc),
                })
            items += vis_items
            visits.append({
                "visit_id": visit_id, "visit_date": d, "patient_id": pid,
                "last_name": last, "first_name": first, "gender": gender,
                "author": rnd.choice(AUTHORS), "comment": rnd.choice(COMMENTS),
                "total_sum": float(sum(x["sum"] for x in vis_items)),
                "has_services": bool(vis_items), "source_file": f"Визит № {visit_id}.xls",
            })

    visits_df = pd.DataFrame(visits)
    items_df = pd.DataFrame(items)
    segments = ["Ценные лояльные", "Новые", "Пропал после 1 визита", "Незавершённое лечение",
                "Только гигиена", "Спящие", "Дети и семьи", "Активные"]

    for pid, g in visits_df.groupby("patient_id"):
        vit = items_df[items_df.visit_id.isin(g.visit_id)]
        paid = g[g.total_sum > 0]
        revenue = float(g.total_sum.sum())
        cats = sorted(vit.category.unique()) if len(vit) else []
        patients.append({
            "patient_id": pid, "last_name": g.last_name.iloc[0], "first_name": g.first_name.iloc[0],
            "gender": g.gender.iloc[0], "first_visit": g.visit_date.min(), "last_visit": g.visit_date.max(),
            "n_visits": len(g), "n_paid_visits": len(paid), "revenue": revenue,
            "avg_check": round(revenue / len(paid), 2) if len(paid) else 0.0,
            "days_since_last": (REPORT_DATE - g.visit_date.max()).days,
            "categories": ", ".join(cats),
            "main_doctor": vit.doctor.mode().iloc[0] if len(vit) else None,
            "is_child": "Детская" in cats,
            "segment": rnd.choice(segments), "rfm": f"R{rnd.randint(1,3)}F{rnd.randint(1,3)}M{rnd.randint(1,3)}",
            "ltv_hist": revenue, "ltv_pred": round(revenue * rnd.uniform(0.3, 1.2), 2),
        })
    patients_df = pd.DataFrame(patients)

    offers = []
    for p in patients:
        for k in range(rnd.choice([0, 1, 1, 2])):
            trig = rnd.choice(list(TRIGGERS))
            reason, offer, tone = TRIGGERS[trig]
            ev = round(rnd.uniform(3000, 60000), -2)
            offers.append({
                "offer_id": f"{p['patient_id']}-{trig}", "patient_id": p["patient_id"], "trigger": trig,
                "reason": reason, "offer": offer, "tone": tone,
                "channel": rnd.choice(["call", "sms", "messenger"]),
                "text": TEXTS[tone].format(name="{name}", reason_lc=reason),
                "priority": round(ev * rnd.uniform(0.05, 0.3) / 1000, 2), "expected_value": ev,
                "due_date": REPORT_DATE + timedelta(days=rnd.randint(-30, 30)), "generated_by": "template",
            })
    offers_df = pd.DataFrame(offers).drop_duplicates("offer_id")

    tags = [{"visit_id": v.visit_id, "patient_id": v.patient_id, "tag": tag}
            for v in visits_df.itertuples() for tag in COMMENT_TAGS.get(v.comment, [])]

    return {
        "visits": visits_df, "visit_items": items_df, "services": services,
        "patients": patients_df, "offers": offers_df,
        "comment_tags": pd.DataFrame(tags, columns=["visit_id", "patient_id", "tag"]),
    }
