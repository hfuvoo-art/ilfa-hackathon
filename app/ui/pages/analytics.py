import json

import streamlit as st

from api_client import get

st.title("Графики и выводы")
st.caption("Выводы аналитика по всей базе. Обновляются раз в 10 минут и сразу после загрузки новых визитов.")

# Цвета графиков аналитика → цвета темы сайта (.streamlit/config.toml). Сами графики не меняем.
THEME_COLORS = {"#175b8a": "#2E8A80", "#087e79": "#7C9AA2", "#b96d28": "#C25A70"}


def themed(fig: dict) -> dict:
    text = json.dumps(fig)
    for old, new in THEME_COLORS.items():
        text = text.replace(old, new)
    fig = json.loads(text)
    for trace in fig["data"]:
        if trace.get("type") == "heatmap":
            trace["colorscale"] = "Teal"
    return fig


@st.cache_data(ttl=600, show_spinner="Строим графики…")  # расчёт по всей базе занимает несколько секунд
def charts():
    return get("/charts")


data = charts()
if not data:
    st.info("Графики строятся только по реальной базе. Сейчас приложение работает на фейковых данных.")
    st.stop()

for fig in data.values():
    # Вывод под графиком аналитик кладёт подписью внутри рисунка: она наезжает на оси и обрезается.
    # Показываем его обычным текстом под графиком.
    notes = fig["layout"].pop("annotations", [])
    st.plotly_chart(themed(fig), use_container_width=True)
    for note in notes:
        st.caption(note["text"])
