import pandas as pd
import streamlit as st

from api_client import get, source_badge

st.title("👥 Сегменты пациентов")
source_badge()

s = get("/stats")
m = st.columns(4)
m[0].metric("Пациентов", s["patients"])
m[1].metric("Визитов", s["visits"])
m[2].metric("Выручка, ₽", f"{s['revenue']:,.0f}".replace(",", " "))
m[3].metric("Визитов без услуг", s["visits_without_services"])

seg = get("/segments")
if not seg:
    st.info("Сегменты появятся, когда аналитик заполнит patients.segment.")
    st.stop()

df = pd.DataFrame(seg)
c1, c2 = st.columns(2)
c1.subheader("Пациентов в сегменте")
c1.bar_chart(df.set_index("segment")["patients"], horizontal=True)
c2.subheader("Выручка сегмента, ₽")
c2.bar_chart(df.set_index("segment")["revenue"], horizontal=True)

st.dataframe(df.rename(columns={"segment": "Сегмент", "patients": "Пациентов", "revenue": "Выручка, ₽",
                                "avg_check": "Средний чек, ₽", "ltv_pred": "Прогноз LTV, ₽"}),
             hide_index=True, use_container_width=True)

st.subheader("Выгрузка сегмента для рассылки")
choice = st.selectbox("Сегмент", df["segment"].tolist())
patients = pd.DataFrame(get("/patients", segment=choice, limit=5000))
st.caption(f"{len(patients)} пациентов")
st.download_button("Скачать CSV", patients.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"segment_{choice}.csv", mime="text/csv")
