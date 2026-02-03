.PHONY: test test-integration lint

test:
	pytest -q

test-integration:
	pytest -q -m integration

lint:
	ruff check .
