import pandas as pd
import streamlit as st

from api_client import CHANNELS, RESULTS, TONES, TRIGGERS, get, post, source_badge

st.title("📞 Кому позвонить сегодня")
source_badge()

meta = get("/meta")
c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
segment = c1.selectbox("Сегмент", ["Все"] + meta["segments"])
trigger = c2.selectbox("Повод", ["Все"] + meta["triggers"], format_func=lambda t: TRIGGERS.get(t, t))
doctor = c3.selectbox("Врач", ["Все"] + meta["doctors"])
limit = c4.number_input("Сколько", 5, 500, 30, step=5)

rows = get("/calls", segment=segment, trigger=trigger, doctor=doctor, limit=limit)
if not rows:
    st.info("Нет пациентов с поводом для контакта по этим фильтрам.")
    st.stop()

st.caption(f"Найдено: {len(rows)}. Отсортировано по приоритету: сверху те, кому звонить в первую очередь.")

for r in rows:
    with st.container(border=True):
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"**{r['last_name']} {r['first_name']}** · {r.get('segment') or '—'}")
            st.markdown(f"**Повод:** {r['reason']}  \n**Предложение:** {r['offer']}")
            st.caption(f"Тон: {TONES.get(r['tone'], r['tone'])} · Канал: {CHANNELS.get(r['channel'], r['channel'])} · "
                       f"Последний визит: {r.get('days_since_last', '—')} дн. назад · "
                       f"Приоритет: {r['priority']}")
            st.code(r["text"], language=None, wrap_lines=True)  # у st.code есть кнопка «скопировать»
        with right:
            if r.get("last_result"):
                st.success(f"Последний результат: {RESULTS.get(r['last_result'], r['last_result'])}")
            res = st.selectbox("Результат", list(RESULTS), format_func=RESULTS.get, key=f"res_{r['offer_id']}")
            note = st.text_input("Комментарий", key=f"note_{r['offer_id']}")
            b1, b2 = st.columns(2)
            if b1.button("Сохранить", key=f"save_{r['offer_id']}", type="primary"):
                resp = post("/contacts", json={"patient_id": r["patient_id"], "offer_id": r["offer_id"],
                                               "result": res, "note": note})
                st.toast("Сохранено" if resp.ok else f"Ошибка: {resp.text}")
                st.rerun()
            if b2.button("Карточка", key=f"card_{r['offer_id']}"):
                st.session_state["patient_id"] = r["patient_id"]
                st.switch_page("pages/patient.py")
