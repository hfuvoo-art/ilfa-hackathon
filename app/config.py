"""Настройки приложения из переменных окружения."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'ilfa.db'}")
API_URL = os.getenv("API_URL", "http://localhost:8000")

# auto  — брать данные из базы, если в ней есть таблицы контракта, иначе фейковые
# true  — всегда фейковые данные (fixtures.py)
# false — только база (ошибка, если таблиц нет)
USE_FIXTURES = os.getenv("USE_FIXTURES", "auto").lower()
