.PHONY: test test-integration lint format precommit

test:
	pytest -q

test-integration:
	pytest -q -m integration

lint:
	ruff check .

format:
	ruff format .
	ruff check . --fix

precommit:
	pre-commit run --all-files
