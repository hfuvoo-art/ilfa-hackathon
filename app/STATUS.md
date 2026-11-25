# STATUS — app

## Сделано
- Каркас: FastAPI (все эндпоинты из плана), Streamlit (4 экрана), Docker Compose, Makefile, .env.example.
- Фейковые данные по контракту (`app/fixtures.py`), автопереключение на настоящую базу (`app/repository.py`).
- Таблица `contacts` и отметка результата звонка.

## В работе
- —

## Сделано позже
- Подключено к базе etl: Docker читает SQLite `data/ilfa.db`, загрузка xls вызывает `etl.load.load`.

## Блокеры / жду от других
- analytics: `patients.segment`, `ltv_pred`.
- offers: таблица `offers`, функция `offers.build.regenerate(patient_id)`.

## Отдал другим
- Описание того, что app ждёт от каждой роли: `app/README.md`.
