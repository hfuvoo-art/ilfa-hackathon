# app/ — API и интерфейс

Владелец: Fullstack. План: [AGENTS.md](AGENTS.md). Статус: [STATUS.md](STATUS.md).

## Запуск

Без Docker (два терминала):
```bash
make install
make api   # http://localhost:8000/docs
make ui    # http://localhost:8501
```

В Docker:
```bash
cp .env.example .env
docker compose up --build              # db + api + ui
docker compose run --rm etl            # загрузить данные в Postgres (когда etl/ готов)
```

## Откуда берутся данные

`app/repository.py` выбирает источник сам:
- в базе есть таблицы `visits`, `visit_items`, `patients` → читаем базу;
- иначе → фейковые данные из `app/fixtures.py` (30 пациентов, строго по `shared/DATA_CONTRACT.md`).

Пока показаны фейковые данные, в интерфейсе висит предупреждение. Как только data-инженер построит базу, всё переключится без изменений кода.

## Что app ждёт от других ролей

| От кого | Что | Как используется |
|---|---|---|
| etl | таблицы `visits`, `visit_items`, `services`, `patients` в `DATABASE_URL` | все экраны |
| etl | модуль `etl.load` с функцией `main(folder: str) -> dict` (сколько файлов загружено) | экран «Загрузка данных», `POST /upload` |
| analytics | поля `patients.segment`, `rfm`, `ltv_hist`, `ltv_pred` | «Сегменты», фильтры, карточка |
| offers | таблица `offers`, `comment_tags` | «Кому позвонить», карточка |
| offers | функция `offers.build.regenerate(patient_id)` | кнопка «Перегенерировать текст» |

Тексты офферов хранятся с плейсхолдером `{name}`; имя подставляет API при выдаче (персональные данные не уходят в LLM).

## API

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/health` | статус и источник данных (`db` / `fixtures`) |
| GET | `/stats` | общие метрики |
| GET | `/meta` | значения для фильтров |
| GET | `/segments` | сводка по сегментам |
| GET | `/patients?segment=&trigger=&q=&limit=` | список пациентов |
| GET | `/patients/{id}` | карточка: визиты, услуги, теги, контакты |
| GET | `/patients/{id}/offers` | офферы пациента |
| POST | `/patients/{id}/offers/regenerate` | перегенерация (501, пока offers/ не готов) |
| GET | `/calls?segment=&trigger=&doctor=&limit=` | «Кому позвонить сегодня» |
| POST | `/contacts` | результат контакта (`no_answer`, `booked`, `refused`, `call_back`, `sent`) |
| GET | `/contacts?patient_id=` | история контактов |
| POST | `/upload` | загрузка `.xls` в `data/inbox/` + запуск `etl.load` |

## Структура

```
app/
  config.py        настройки из окружения
  fixtures.py      фейковые данные по контракту
  repository.py    доступ к данным (база или фейк), таблица contacts
  api/main.py      FastAPI
  ui/Home.py       Streamlit, навигация
  ui/api_client.py клиент к API, русские подписи
  ui/pages/        calls, patient, segments, upload
```
