# Ilfa Hackathon — «Маркетинг, который помнит каждого пациента»

Интеллектуальный маркетинговый сервис для сети стоматологических клиник «Ильфа»: из 8 652 выгрузок визитов в `.xls` собираем единую базу, сегментируем пациентов, считаем LTV и экономику, генерируем персональные предложения с заботливым тоном и показываем всё в веб-прототипе.

## Команда и зоны

| Роль | Папка | Ветка | План |
|---|---|---|---|
| Руководитель / бизнес-аналитик | `docs/` | `docs` | [docs/AGENTS.md](docs/AGENTS.md) |
| Data-инженер | `etl/` | `etl` | [etl/AGENTS.md](etl/AGENTS.md) |
| Аналитик данных | `analytics/` | `analytics` | [analytics/AGENTS.md](analytics/AGENTS.md) |
| ML/LLM-разработчик | `offers/` | `offers` | [offers/AGENTS.md](offers/AGENTS.md) |
| Fullstack-разработчик | `app/` | `app` | [app/AGENTS.md](app/AGENTS.md) |

Общие файлы:
- [AGENTS.md](AGENTS.md) — правила для ИИ-ассистентов (их читают Cursor, Claude Code, Codex и др.).
- [CONTRIBUTING.md](CONTRIBUTING.md) — правила работы с git для людей.
- [shared/DATA_CONTRACT.md](shared/DATA_CONTRACT.md) — единая схема таблиц.
- `*/STATUS.md` — текущий статус каждой роли.

## Как начать

1. Клонировать репозиторий и создать ветку своей роли (см. [CONTRIBUTING.md](CONTRIBUTING.md)).
2. Положить архив с данными в `data/raw/` и распаковать (см. [data/README.md](data/README.md)). **Данные в git не коммитим.**
3. Открыть репозиторий в своём ИИ-инструменте и написать: «Я <роль>, работаю в папке `<папка>/`. Прочитай AGENTS.md, shared/DATA_CONTRACT.md и <папка>/AGENTS.md и начни по плану».

## Как запустить прототип

```bash
cp .env.example .env
docker compose up --build
```
Интерфейс: http://localhost:8501, API: http://localhost:8000/docs. Без Docker: `make install`, затем `make api` и `make ui` в двух терминалах. Подробнее: [app/README.md](app/README.md).
