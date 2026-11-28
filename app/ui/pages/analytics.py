import streamlit as st

from api_client import get

st.title("📊 Аналитика")
st.caption("Графики и выводы аналитика по всей базе. Пересчитываются раз в 10 минут и после загрузки новых визитов.")


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
    st.plotly_chart(fig, use_container_width=True)
    for note in notes:
        st.caption(note["text"])
