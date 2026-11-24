# Локальный запуск без Docker. Нужен Python 3.11+.
.PHONY: install api ui load offers segments up down

install:
	pip install -r app/requirements.txt
	@for f in etl analytics offers; do [ -f $$f/requirements.txt ] && pip install -r $$f/requirements.txt || true; done

api:
	uvicorn app.api.main:app --reload --port 8000

ui:
	streamlit run app/ui/Home.py

load:        # строит data/ilfa.db (скрипт data-инженера)
	python -m etl.load data/raw/anonymized

segments:    # заполняет сегменты и LTV (скрипт аналитика)
	python -m analytics.segments

offers:      # заполняет таблицу offers (скрипт ML/LLM)
	python -m offers.build

up:
	docker compose up --build

down:
	docker compose down
