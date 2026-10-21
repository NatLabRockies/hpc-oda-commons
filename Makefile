.PHONY: test test-integration lint format precommit docs-cli

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

docs-cli:
	python -m hpc_oda_commons.qst.cli_reference
