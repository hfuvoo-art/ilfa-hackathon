"""Тонкий клиент к API. Интерфейс ходит только в API, не в базу напрямую."""
from __future__ import annotations

import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

RESULTS = {
    "booked": "Записался",
    "no_answer": "Не дозвонились",
    "call_back": "Перезвонить",
    "refused": "Отказ",
    "sent": "Сообщение отправлено",
}
TONES = {"care": "Забота", "calm": "Спокойствие", "reliability": "Надёжность", "light": "Легко и коротко"}
TRIGGERS = {
    "implant_control": "Контроль импланта",
    "hygiene_due": "Пора на гигиену",
    "hygiene_only": "Только гигиена",
    "unfinished_implant": "Незавершённая имплантация",
    "unfinished_ortho": "Незавершённая ортодонтия",
    "lost_after_first": "Пропал после 1 визита",
    "sleeping_valuable": "Спящий ценный",
    "child_checkup": "Осмотр ребёнка",
    "seasonal": "Сезонный повод",
}
CHANNELS = {"call": "Звонок", "sms": "SMS", "messenger": "Мессенджер"}


def get(path: str, **params):
    params = {k: v for k, v in params.items() if v not in (None, "", "Все")}
    try:
        r = requests.get(f"{API_URL}{path}", params=params, timeout=30)
    except requests.ConnectionError:
        st.error(f"API недоступен по адресу {API_URL}. Запустите: make api")
        st.stop()
    r.raise_for_status()
    return r.json()


def post(path: str, json=None, files=None):
    r = requests.post(f"{API_URL}{path}", json=json, files=files, timeout=300)
    return r


def source_badge():
    h = get("/health")
    if h["source"] == "fixtures":
        st.caption("⚠️ Сейчас показаны **фейковые данные**. Настоящая база подключится сама, когда etl/ её построит.")
