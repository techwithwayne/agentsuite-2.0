.PHONY: help run dev test lint fmt

help:
@echo "Targets:"
@echo "  dev  - run with reload"
@echo "  run  - run without reload"
@echo "  test - run tests"
@echo "  lint - ruff (if installed)"
@echo "  fmt  - ruff format (if installed)"

dev:
uvicorn urls:app --host 0.0.0.0 --port 8000 --reload

run:
uvicorn urls:app --host 0.0.0.0 --port 8000

test:
pytest -q

lint:
ruff check .

fmt:
ruff format .
