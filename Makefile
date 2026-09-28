PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

setup:
	$(PIP) install -r requirements.txt
	chmod +x scripts/setup_ollama.sh

run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -q

demo:
	$(PYTHON) -m app.demo
