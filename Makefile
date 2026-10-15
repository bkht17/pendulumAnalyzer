# Секундомер против камеры — основные команды.
# Требования: Python ≥ 3.11, Node.js ≥ 20.

BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

.PHONY: install dev-backend dev-frontend test lint format build run clean-data

install:  ## Установить зависимости бэкенда и фронтенда
	python3 -m venv $(BACKEND)/.venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "$(BACKEND)[dev]"
	npm --prefix $(FRONTEND) ci

dev-backend:  ## API с автоперезагрузкой на :8000
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:  ## Vite на :5173 (проксирует /api на :8000)
	npm --prefix $(FRONTEND) run dev

test:  ## Все тесты
	cd $(BACKEND) && .venv/bin/python -m pytest
	npm --prefix $(FRONTEND) test

lint:  ## Линтеры и проверка типов
	cd $(BACKEND) && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
	npm --prefix $(FRONTEND) run lint
	npm --prefix $(FRONTEND) run typecheck

format:  ## Автоформатирование Python
	cd $(BACKEND) && .venv/bin/ruff format app tests && .venv/bin/ruff check --fix app tests

build:  ## Собрать фронтенд (FastAPI будет раздавать его сам)
	npm --prefix $(FRONTEND) run build

run: build  ## Одно приложение на :8000 — API + собранный интерфейс
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --port 8000

clean-data:  ## Удалить базу и все загруженные видео
	rm -rf data
