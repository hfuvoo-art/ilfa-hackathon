import pandas as pd
import streamlit as st

from api_client import CHANNELS, RESULTS, TONES, TRIGGERS, get, post, source_badge

st.title("🧾 Карточка пациента")
source_badge()

q = st.text_input("Поиск по фамилии или имени", placeholder="Например: Фамилия 12")
found = get("/patients", q=q, limit=200)
if not found:
    st.info("Никого не нашли.")
    st.stop()

ids = [p["patient_id"] for p in found]
labels = {p["patient_id"]: f"{p['last_name']} {p['first_name']} · {p.get('segment') or '—'}" for p in found}
current = st.session_state.get("patient_id")
idx = ids.index(current) if current in ids else 0
pid = st.selectbox("Пациент", ids, index=idx, format_func=labels.get)
st.session_state["patient_id"] = pid

card = get(f"/patients/{pid}")
p = card["patient"]

m = st.columns(5)
m[0].metric("Сегмент", p.get("segment") or "—")
m[1].metric("Визитов", p["n_visits"])
m[2].metric("Выручка, ₽", f"{p['revenue']:,.0f}".replace(",", " "))
m[3].metric("Прогноз LTV, ₽", f"{p['ltv_pred']:,.0f}".replace(",", " ") if p.get("ltv_pred") is not None else "—")
m[4].metric("Дней с визита", p["days_since_last"])
st.caption(f"Пол: {p['gender']} · Первый визит: {p['first_visit']} · Последний: {p['last_visit']} · "
           f"Врач: {p.get('main_doctor') or '—'} · Категории: {p.get('categories') or '—'}"
           + (f" · Теги: {', '.join(card['tags'])}" if card["tags"] else ""))

st.subheader("Персональные предложения")
offers = get(f"/patients/{pid}/offers")
if not offers:
    st.caption("Повода для контакта нет.")
for o in offers:
    with st.container(border=True):
        st.markdown(f"**{TRIGGERS.get(o['trigger'], o['trigger'])}** — {o['reason']}. Предложение: {o['offer']}")
        st.caption(f"Тон: {TONES.get(o['tone'], o['tone'])} · Канал: {CHANNELS.get(o['channel'], o['channel'])} · "
                   f"Ожидаемая выручка: {o['expected_value']:,.0f} ₽ · Источник текста: {o['generated_by']}".replace(",", " "))
        st.code(o["text"], language=None, wrap_lines=True)
        if st.button("Перегенерировать текст", key=f"regen_{o['offer_id']}"):
            r = post(f"/patients/{pid}/offers/regenerate")
            st.toast("Готово" if r.ok else r.json().get("detail", r.text))

st.subheader("История визитов")
for v in card["visits"]:
    title = f"{v['visit_date']} · {v['total_sum']:,.0f} ₽".replace(",", " ") + ("" if v["has_services"] else " · без услуг")
    with st.expander(title):
        if v["items"]:
            df = pd.DataFrame(v["items"])[["service_name", "category", "doctor", "qty", "price", "sum", "discount"]]
            df.columns = ["Услуга", "Категория", "Врач", "Кол-во", "Цена", "Сумма", "Скидка"]
            st.dataframe(df, hide_index=True, use_container_width=True)
        if v.get("comment"):
            st.caption(f"Комментарий администратора: {v['comment']}")

if card["contacts"]:
    st.subheader("Контакты с пациентом")
    c = pd.DataFrame(card["contacts"])
    c["result"] = c["result"].map(RESULTS).fillna(c["result"])
    st.dataframe(c[["created_at", "result", "note"]].rename(
        columns={"created_at": "Когда", "result": "Результат", "note": "Комментарий"}), hide_index=True)
