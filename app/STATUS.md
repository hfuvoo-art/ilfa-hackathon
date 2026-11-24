# STATUS — app

## Сделано
- Каркас: FastAPI (все эндпоинты из плана), Streamlit (4 экрана), Docker Compose, Makefile, .env.example.
- Фейковые данные по контракту (`app/fixtures.py`), автопереключение на настоящую базу (`app/repository.py`).
- Таблица `contacts` и отметка результата звонка.

## В работе
- —

## Блокеры / жду от других
- etl: база с таблицами контракта; модуль `etl.load` с `main(folder) -> dict`.
- analytics: `patients.segment`, `ltv_pred`.
- offers: таблица `offers`, функция `offers.build.regenerate(patient_id)`.

## Отдал другим
- Описание того, что app ждёт от каждой роли: `app/README.md`.
