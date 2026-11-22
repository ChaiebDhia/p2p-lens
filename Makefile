.PHONY: install check lint format test demo build clean

install:
	pip install -e ".[dev,plots]"

lint:
	ruff check .
	ruff format --check .
	mypy src

test:
	pytest

check: lint test

format:
	ruff check . --fix
	ruff format .

demo:
	p2p-lens demo --out out

build:
	python -m build

clean:
	rm -rf out dist build .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
