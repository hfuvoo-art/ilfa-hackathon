"""Точка входа Streamlit. Запуск: streamlit run app/ui/Home.py"""
import hmac
import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Ильфа — пациенты", page_icon="🦷", layout="wide")
st.logo(str(Path(__file__).parent / "logo.svg"), size="large")

# Вход по паролю из APP_PASSWORD. Если переменная пустая (локальная разработка) — без пароля.
PASSWORD = os.getenv("APP_PASSWORD", "")


def login():
    st.title("Ильфа")
    st.caption("Маркетинг, который помнит каждого пациента. Введите пароль, который выдал администратор стенда.")
    entered = st.text_input("Пароль", type="password")
    if entered and hmac.compare_digest(entered, PASSWORD):
        st.session_state["authed"] = True
        st.rerun()
    if entered:
        st.error("Неверный пароль")


if PASSWORD and not st.session_state.get("authed"):
    # st.navigation вызываем всегда: иначе Streamlit сам откроет страницы из pages/ по прямой ссылке
    pages = [st.Page(login, title="Вход", icon=":material/lock:")]
else:
    pages = {
        "Работа с пациентами": [
            st.Page("pages/calls.py", title="Кому позвонить сегодня", icon=":material/call:", default=True),
            st.Page("pages/patient.py", title="Карточка пациента", icon=":material/person:"),
        ],
        "Аналитика": [
            st.Page("pages/segments.py", title="Сегменты", icon=":material/groups:"),
            st.Page("pages/analytics.py", title="Графики и выводы", icon=":material/monitoring:"),
        ],
        "Данные": [
            st.Page("pages/upload.py", title="Загрузка визитов", icon=":material/upload_file:"),
        ],
    }
st.navigation(pages).run()
