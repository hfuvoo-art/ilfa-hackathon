import streamlit as st

from api_client import post, source_badge

st.title("📥 Загрузка новых визитов")
source_badge()
st.write("У медицинской системы нет API, поэтому новые визиты выгружаются в `.xls`. "
         "Загрузите файлы сюда: они попадут в `data/inbox/`, и загрузчик добавит в базу только новые визиты.")

files = st.file_uploader("Файлы «Визит № ….xls»", type=["xls"], accept_multiple_files=True)
if files and st.button("Загрузить", type="primary"):
    payload = [("files", (f.name, f.getvalue(), "application/vnd.ms-excel")) for f in files]
    with st.spinner("Загружаем…"):
        r = post("/upload", files=payload)
    if r.ok:
        data = r.json()
        st.success(f"Сохранено файлов: {len(data['saved'])}")
        st.info(data.get("message") or f"Результат загрузки: {data.get('result')}")
    else:
        st.error(r.text)
