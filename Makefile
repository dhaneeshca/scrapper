SHELL  := /bin/bash
VENV   := .venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python

.PHONY: setup run dev build seed db-start db-check _venv _npm _playwright check-tools _ensure-db

# ── Primary targets ────────────────────────────────────────────────────────────

setup: .env check-tools db-start _venv _playwright _npm seed
	@echo ""
	@echo "  Setup complete. Run 'make run' to start."

run: build
	$(PY) main.py

dev:
	$(PY) dev.py

# ── Tool checks ────────────────────────────────────────────────────────────────

check-tools:
	@command -v python3 >/dev/null 2>&1 || { \
		echo "Python 3 not found."; \
		if command -v brew >/dev/null 2>&1; then brew install python; \
		else echo "Install Python 3 from https://python.org"; exit 1; fi; \
	}
	@command -v node >/dev/null 2>&1 || { \
		echo "Node.js not found."; \
		if command -v brew >/dev/null 2>&1; then brew install node; \
		else echo "Install Node.js from https://nodejs.org"; exit 1; fi; \
	}
	@pg_isready -q 2>/dev/null || command -v createdb >/dev/null 2>&1 || { \
		echo "PostgreSQL not found."; \
		if command -v brew >/dev/null 2>&1; then brew install postgresql@16 && brew link postgresql@16; \
		else echo "Install PostgreSQL from https://postgresql.org"; exit 1; fi; \
	}

# ── Database ───────────────────────────────────────────────────────────────────

db-start:
	@pg_isready -q 2>/dev/null && echo "PostgreSQL is already running." || { \
		echo "Starting PostgreSQL..."; \
		brew services start postgresql@16 2>/dev/null || brew services start postgresql 2>/dev/null; \
		sleep 2; \
		pg_isready -q && echo "PostgreSQL started." || { echo "Could not start PostgreSQL."; exit 1; }; \
	}
	@$(MAKE) --no-print-directory _ensure-db

_ensure-db:
	@DB_NAME=$$(grep DATABASE_URL .env | cut -d/ -f4 | cut -d? -f1); \
	psql -lqt 2>/dev/null | cut -d\| -f1 | grep -qw "$$DB_NAME" || \
		(echo "Creating database $$DB_NAME..." && createdb "$$DB_NAME")

db-check:
	@pg_isready -q 2>/dev/null || { echo "PostgreSQL is not running. Run: make db-start"; exit 1; }

# ── Python venv ────────────────────────────────────────────────────────────────

_venv:
	@[ -f $(VENV)/bin/activate ] || python3 -m venv $(VENV)
	@echo "Installing Python dependencies..."
	@$(PIP) install -q -r requirements.txt

_playwright:
	@echo "Installing Playwright browser (Chromium)..."
	@$(PY) -m playwright install chromium --with-deps 2>/dev/null || $(PY) -m playwright install chromium

# ── Node / frontend ────────────────────────────────────────────────────────────

_npm:
	@echo "Installing frontend dependencies..."
	@cd web && npm install --silent

build:
	@cd web && npm run build --silent

# ── Env file ───────────────────────────────────────────────────────────────────

.env:
	@echo "Creating .env from .env.example..."
	@cp .env.example .env
	@echo "  Edit .env if your DATABASE_URL differs from the default."

# ── Config seed ────────────────────────────────────────────────────────────────

seed: db-check _venv
	@$(PY) seed.py
