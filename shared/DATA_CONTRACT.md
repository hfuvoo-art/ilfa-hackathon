# Контракт данных (единая схема для всех ролей)

**Это общий договор команды.** Все роли используют ровно эти имена таблиц и полей. Менять только по согласованию в общем чате, отдельным PR с префиксом `shared:`.

## Где лежат данные и как их получить

- Сырые файлы: `data/raw/anonymized/*.xls` (у каждого локально, в git не попадают).
- База: `data/ilfa.db` (SQLite) локально, или PostgreSQL в Docker. Подключение: переменная `DATABASE_URL`, по умолчанию `sqlite:///data/ilfa.db`.
- **База строится скриптом data-инженера** (будет в `etl/`, команда запуска появится в `etl/README.md`). Каждый участник запускает его у себя, чтобы получить одинаковую базу. Сам файл базы не коммитим.
- Пока скрипт не готов: data-инженер выкладывает в общий чат (не в git!) черновой CSV, остальные работают на нём.

## Ключи

- `visit_id` — целое число из поля `№` файла визита.
- `patient_id` — строка: первые 12 символов `sha1` от нормализованной строки `"<фамилия>|<имя>"` (обрезать пробелы, нижний регистр, `ё`→`е`). Одинаковая функция во всех модулях — её реализует `etl/`, остальные импортируют оттуда.

## Таблицы

### `visits` — один визит (владелец: etl)
| Поле | Тип | Описание |
|---|---|---|
| visit_id | int, PK | номер визита |
| visit_date | date | дата визита |
| patient_id | text | ключ пациента |
| last_name | text | фамилия (анонимизированная) |
| first_name | text | имя (анонимизированное) |
| gender | text | `F` / `M` / `unknown` (после восстановления по другим визитам) |
| author | text | администратор, оформивший визит |
| comment | text | комментарий администратора (может быть пустым) |
| total_sum | real | сумма по всем услугам визита, ₽ |
| has_services | bool | есть ли в визите услуги |
| source_file | text | имя исходного файла |

### `visit_items` — услуга в визите (владелец: etl)
| Поле | Тип | Описание |
|---|---|---|
| visit_id | int, FK → visits | |
| service_name | text | нормализованное название услуги |
| category | text | категория из `services.category` |
| doctor | text | врач, нормализованное ФИО (регистр «Иванов Иван Иванович») |
| qty | real | количество |
| price | real | цена по прайсу, ₽ |
| sum | real | фактическая сумма, ₽ |
| discount | real | `price*qty - sum`, не меньше 0 |

### `services` — справочник услуг (владелец: etl, категории согласует с analytics и offers)
| Поле | Тип | Описание |
|---|---|---|
| service_name | text, PK | |
| category | text | одна из: `Терапия`, `Гигиена`, `Хирургия`, `Имплантация`, `Ортопедия`, `Ортодонтия`, `Детская`, `Диагностика`, `Консультация`, `Прочее` |
| follow_up_days | int, null | через сколько дней нужен контроль/повтор (гигиена 180, имплантация 365, ортодонтия 45 и т. д.) |
| is_chain_start | bool | после этой услуги ожидается продолжение лечения |

### `patients` — витрина пациента (базовые поля: etl; `segment`, `ltv*`: analytics)
| Поле | Тип | Владелец | Описание |
|---|---|---|---|
| patient_id | text, PK | etl | |
| last_name, first_name | text | etl | |
| gender | text | etl | `F` / `M` / `unknown` |
| first_visit, last_visit | date | etl | |
| n_visits | int | etl | все визиты |
| n_paid_visits | int | etl | визиты с услугами и суммой > 0 |
| revenue | real | etl | сумма за весь период, ₽ |
| avg_check | real | etl | revenue / n_paid_visits |
| days_since_last | int | etl | дней от last_visit до даты отчёта (по умолчанию максимальная дата в данных) |
| categories | text | etl | категории услуг через запятую |
| main_doctor | text | etl | самый частый врач |
| is_child | bool | etl | были детские услуги |
| segment | text | analytics | бизнес-сегмент (см. `analytics/AGENTS.md`) |
| rfm | text | analytics | код RFM, например `R3F2M3` |
| ltv_hist | real | analytics | фактическая выручка |
| ltv_pred | real | analytics | прогнозный LTV на 12 мес. |

### `comment_tags` — признаки из комментариев (владелец: offers)
| Поле | Тип | Описание |
|---|---|---|
| visit_id | int | |
| patient_id | text | |
| tag | text | `anxious`, `parent`, `pregnant_or_nursing`, `price_sensitive`, `thinking`, `complex_case`, … |

### `offers` — персональные предложения (владелец: offers)
| Поле | Тип | Описание |
|---|---|---|
| offer_id | text, PK | |
| patient_id | text | |
| trigger | text | код повода: `implant_control`, `hygiene_due`, `hygiene_only`, `unfinished_implant`, `unfinished_ortho`, `lost_after_first`, `sleeping_valuable`, `child_checkup`, `seasonal` |
| reason | text | человекочитаемый повод («прошёл год после установки импланта») |
| offer | text | что предлагаем |
| tone | text | `care`, `calm`, `reliability`, `light` |
| channel | text | `call`, `sms`, `messenger` |
| text | text | готовый текст для пациента |
| priority | real | чем больше, тем раньше связываться |
| expected_value | real | ожидаемая выручка, ₽ |
| due_date | date | когда лучше связаться |
| generated_by | text | `template` или `llm` |

### `contacts` — результат контакта с пациентом (владелец: app)
| Поле | Тип | Описание |
|---|---|---|
| contact_id | int, PK | |
| patient_id | text | |
| offer_id | text, null | |
| result | text | `no_answer`, `booked`, `refused`, `call_back`, `sent` |
| note | text | |
| created_at | timestamp | |

## Кто что пишет в базу

| Таблица | Пишет | Читают |
|---|---|---|
| visits, visit_items, services | etl | все |
| patients (базовые поля) | etl | все |
| patients.segment / rfm / ltv_* | analytics | offers, app, docs |
| comment_tags, offers | offers | app, docs |
| contacts | app | analytics, docs |
