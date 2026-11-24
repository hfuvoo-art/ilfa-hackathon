"""Точка входа Streamlit. Запуск: streamlit run app/ui/Home.py"""
import streamlit as st

st.set_page_config(page_title="Ильфа · пациенты", page_icon="🦷", layout="wide")

pages = [
    st.Page("pages/calls.py", title="Кому позвонить сегодня", icon="📞", default=True),
    st.Page("pages/patient.py", title="Карточка пациента", icon="🧾"),
    st.Page("pages/segments.py", title="Сегменты", icon="👥"),
    st.Page("pages/upload.py", title="Загрузка данных", icon="📥"),
]
st.navigation(pages).run()
