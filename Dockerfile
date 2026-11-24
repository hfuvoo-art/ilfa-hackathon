FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

# Зависимости всех ролей: у кого появится requirements.txt — подхватится при сборке
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt
COPY . .
RUN for f in etl analytics offers; do \
      if [ -f $f/requirements.txt ]; then pip install --no-cache-dir -r $f/requirements.txt; fi; \
    done
