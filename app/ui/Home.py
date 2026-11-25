"""Точка входа Streamlit. Запуск: streamlit run app/ui/Home.py"""
import hmac
import os

import streamlit as st

st.set_page_config(page_title="Ильфа · пациенты", page_icon="🦷", layout="wide")

# Вход по паролю из APP_PASSWORD. Если переменная пустая (локальная разработка) — без пароля.
PASSWORD = os.getenv("APP_PASSWORD", "")


def login():
    st.title("🦷 Ильфа · пациенты")
    entered = st.text_input("Пароль", type="password")
    if entered and hmac.compare_digest(entered, PASSWORD):
        st.session_state["authed"] = True
        st.rerun()
    if entered:
        st.error("Неверный пароль")


if PASSWORD and not st.session_state.get("authed"):
    # st.navigation вызываем всегда: иначе Streamlit сам откроет страницы из pages/ по прямой ссылке
    pages = [st.Page(login, title="Вход", icon="🔒")]
else:
    pages = [
        st.Page("pages/calls.py", title="Кому позвонить сегодня", icon="📞", default=True),
        st.Page("pages/patient.py", title="Карточка пациента", icon="🧾"),
        st.Page("pages/segments.py", title="Сегменты", icon="👥"),
        st.Page("pages/upload.py", title="Загрузка данных", icon="📥"),
    ]
st.navigation(pages).run()
