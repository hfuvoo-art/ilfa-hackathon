import pandas as pd
import streamlit as st

from api_client import get, header, rub

header("Сегменты пациентов", "Из кого состоит база клиники и сколько приносит каждая группа.")

s = get("/stats")
m = st.columns(4)
m[0].metric("Пациентов", f"{s['patients']:,}".replace(",", "\u00a0"), border=True)
m[1].metric("Визитов", f"{s['visits']:,}".replace(",", "\u00a0"), border=True)
m[2].metric("Выручка", rub(s["revenue"]), border=True)
m[3].metric("Визитов без услуг", f"{s['visits_without_services']:,}".replace(",", "\u00a0"), border=True)

seg = get("/segments")
if not seg:
    st.info("Сегменты появятся, когда аналитик заполнит patients.segment.")
    st.stop()

df = pd.DataFrame(seg)
c1, c2 = st.columns(2)
c1.subheader("Пациентов в сегменте")
c1.bar_chart(df.set_index("segment")["patients"], horizontal=True)
c2.subheader("Выручка сегмента, млн ₽")
c2.bar_chart((df.set_index("segment")["revenue"] / 1_000_000).round(1), horizontal=True)

money = {"format": "localized"}  # разделители тысяч по языку браузера
st.dataframe(df.round(0), hide_index=True, use_container_width=True, column_config={
    "segment": "Сегмент",
    "patients": "Пациентов",
    "revenue": st.column_config.NumberColumn("Выручка, ₽", **money),
    "avg_check": st.column_config.NumberColumn("Средний чек, ₽", **money),
    "ltv_pred": st.column_config.NumberColumn("Прогноз LTV, ₽", **money),
})

st.subheader("Выгрузка сегмента для рассылки")
choice = st.selectbox("Сегмент", df["segment"].tolist())
patients = pd.DataFrame(get("/patients", segment=choice, limit=5000))
st.caption(f"{len(patients)} пациентов")
st.download_button("Скачать CSV", patients.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"segment_{choice}.csv", mime="text/csv")
