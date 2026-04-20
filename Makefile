.PHONY: help install dev run test clean lint format

help:
	@echo "MCP Control Plane (Dema) - Makefile"
	@echo "===================================="
	@echo ""
	@echo "Available commands:"
	@echo "  make install     - Install dependencies"
	@echo "  make dev         - Install development dependencies"
	@echo "  make run         - Run the server"
	@echo "  make cli         - Run the CLI tool"
	@echo "  make examples    - Run example workflows"
	@echo "  make test        - Run tests"
	@echo "  make lint        - Run linters"
	@echo "  make format      - Format code"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make docs        - Build documentation"

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov pylint black flake8

run:
	python main.py

cli:
	python cli.py

examples:
	python examples.py

test:
	pytest tests/ -v

test-coverage:
	pytest tests/ --cov=. --cov-report=html

lint:
	pylint *.py
	flake8 *.py

format:
	black *.py

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docs:
	@echo "Documentation in README.md"

.DEFAULT_GOAL := help
