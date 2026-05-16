.PHONY: setup dev run build

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements.txt
	.venv/bin/playwright install chromium
	cd web && npm install

dev:
	.venv/bin/python dev.py

build:
	cd web && npm run build

run: build
	.venv/bin/python main.py
