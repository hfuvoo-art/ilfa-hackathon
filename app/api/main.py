"""FastAPI: API для интерфейса администратора и маркетолога.

Запуск: uvicorn app.api.main:app --reload
Документация: http://localhost:8000/docs
"""
from __future__ import annotations

import importlib
import io
import math
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app import config, repository as repo
from etl.load import load

app = FastAPI(title="Ilfa — маркетинг, который помнит каждого пациента", version="0.1.0")

INBOX = config.ROOT / "data" / "inbox"


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → JSON-совместимый список словарей (NaN → None, даты → ISO)."""
    out = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if isinstance(v, float) and math.isnan(v):
                v = None
            elif isinstance(v, pd.Timestamp) and v == v.normalize():
                v = v.date().isoformat()  # SQLite отдаёт DATE как дату со временем 00:00
            elif isinstance(v, (pd.Timestamp, datetime, date)):
                v = v.isoformat()
            elif hasattr(v, "item"):  # numpy-типы
                v = v.item()
            clean[k] = v
        out.append(clean)
    return out


def personalize(offers: pd.DataFrame, patients: pd.DataFrame) -> pd.DataFrame:
    """Подставить имя в текст оффера. Имя добавляется только здесь, после генерации (правило про LLM)."""
    if offers.empty:
        return offers
    names = patients.set_index("patient_id")["first_name"]
    offers = offers.copy()
    offers["text"] = [
        str(t).replace("{name}", str(names.get(pid, ""))) for t, pid in zip(offers["text"], offers["patient_id"])
    ]
    return offers


@app.get("/health")
def health():
    return {"status": "ok", "source": repo.source()}


@app.get("/stats")
def stats():
    v, p, it = repo.table("visits"), repo.table("patients"), repo.table("visit_items")
    return {
        "source": repo.source(),
        "visits": len(v),
        "patients": len(p),
        "service_lines": len(it),
        "revenue": float(it["sum"].sum()) if len(it) else 0.0,
        "visits_without_services": int((~v["has_services"].astype(bool)).sum()) if len(v) else 0,
        "period": [str(pd.Timestamp(v.visit_date.min()).date()), str(pd.Timestamp(v.visit_date.max()).date())] if len(v) else None,
    }


@app.get("/segments")
def segments():
    p = repo.table("patients")
    if p.empty or "segment" not in p or p["segment"].isna().all():
        return []
    g = p.groupby("segment").agg(patients=("patient_id", "count"), revenue=("revenue", "sum"),
                                 avg_check=("avg_check", "mean"), ltv_pred=("ltv_pred", "mean"))
    g = g.reset_index().sort_values("revenue", ascending=False)
    return records(g.round(2))


@app.get("/patients")
def patients(segment: str | None = None, trigger: str | None = None, q: str | None = None,
             limit: int = Query(100, le=5000)):
    p = repo.table("patients")
    if segment:
        p = p[p["segment"] == segment]
    if trigger:
        o = repo.table("offers")
        p = p[p["patient_id"].isin(o.loc[o["trigger"] == trigger, "patient_id"])]
    if q:
        ql = q.lower()
        p = p[(p["last_name"] + " " + p["first_name"]).str.lower().str.contains(ql, regex=False)]
    return records(p.sort_values("revenue", ascending=False).head(limit))


@app.get("/patients/{patient_id}")
def patient_card(patient_id: str):
    p = repo.table("patients")
    row = p[p["patient_id"] == patient_id]
    if row.empty:
        raise HTTPException(404, "Пациент не найден")
    v = repo.table("visits")
    v = v[v["patient_id"] == patient_id].sort_values("visit_date", ascending=False)
    it = repo.table("visit_items")
    it = it[it["visit_id"].isin(v["visit_id"])]
    tags = repo.table("comment_tags")
    tags = sorted(tags.loc[tags["patient_id"] == patient_id, "tag"].unique()) if len(tags) else []
    visits = []
    for rec in records(v):
        rec["items"] = records(it[it["visit_id"] == rec["visit_id"]])
        visits.append(rec)
    return {"patient": records(row)[0], "visits": visits, "tags": tags,
            "contacts": records(repo.contacts(patient_id))}


@app.get("/patients/{patient_id}/offers")
def patient_offers(patient_id: str):
    o = repo.table("offers")
    if o.empty:
        return []
    o = o[o["patient_id"] == patient_id].sort_values("priority", ascending=False)
    return records(personalize(o, repo.table("patients")))


@app.post("/patients/{patient_id}/offers/regenerate")
def regenerate(patient_id: str):
    """Перегенерация текста. Заработает, когда offers/ предоставит функцию regenerate(patient_id)."""
    try:
        mod = importlib.import_module("offers.build")
        fn = getattr(mod, "regenerate")
    except (ImportError, AttributeError):
        raise HTTPException(501, "Перегенерация появится, когда будет готов модуль offers/")
    fn(patient_id)
    return patient_offers(patient_id)


@app.get("/calls")
def calls(segment: str | None = None, trigger: str | None = None, doctor: str | None = None,
          limit: int = Query(50, le=1000)):
    """Список «Кому позвонить сегодня»: лучший оффер на пациента, по убыванию приоритета."""
    o, p = repo.table("offers"), repo.table("patients")
    if o.empty:
        return []
    o = o.sort_values("priority", ascending=False).drop_duplicates("patient_id")
    cols = ["patient_id", "last_name", "first_name", "segment", "main_doctor", "days_since_last", "revenue"]
    o = o.merge(p[[c for c in cols if c in p]], on="patient_id", how="left")
    if segment:
        o = o[o["segment"] == segment]
    if trigger:
        o = o[o["trigger"] == trigger]
    if doctor:
        o = o[o["main_doctor"] == doctor]
    done = repo.contacts()
    if len(done):
        o["last_result"] = o["patient_id"].map(done.drop_duplicates("patient_id").set_index("patient_id")["result"])
    else:
        o["last_result"] = None
    return records(personalize(o.head(limit), p))


class ContactIn(BaseModel):
    patient_id: str
    result: Literal["no_answer", "booked", "refused", "call_back", "sent"]
    offer_id: str | None = None
    note: str | None = None


@app.post("/contacts")
def add_contact(c: ContactIn):
    return records(pd.DataFrame([repo.add_contact(c.patient_id, c.result, c.offer_id, c.note)]))[0]


@app.get("/contacts")
def list_contacts(patient_id: str | None = None):
    return records(repo.contacts(patient_id))


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    """Принять новые .xls в data/inbox/ и загрузить их в базу загрузчиком etl."""
    # Каждая загрузка — в свою папку, чтобы битый файл не мешал следующим загрузкам
    batch = INBOX / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    batch.mkdir(parents=True)
    saved = []
    for f in files:
        name = Path(f.filename or "").name
        if not name.lower().endswith(".xls"):
            raise HTTPException(400, f"Не .xls файл: {name}")
        (batch / name).write_bytes(await f.read())
        saved.append(name)
    log = io.StringIO()
    try:
        with redirect_stdout(log):  # load() пишет итоги загрузки в stdout
            load(batch)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {"saved": saved, "message": log.getvalue().strip()}


@app.get("/meta")
def meta():
    """Значения для фильтров интерфейса."""
    p, o = repo.table("patients"), repo.table("offers")
    return {
        "segments": sorted(p["segment"].dropna().unique()) if "segment" in p else [],
        "triggers": sorted(o["trigger"].dropna().unique()) if len(o) else [],
        "doctors": sorted(p["main_doctor"].dropna().unique()) if "main_doctor" in p else [],
    }
