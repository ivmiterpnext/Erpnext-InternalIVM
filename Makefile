SHELL := /bin/bash
.DEFAULT_GOAL := help

help:
	@echo "Available Commands:"
	@echo " -- make setup"
	@echo "  > Run first time developer setup"
	@echo " -- make run"
	@echo "  > Start frappe development environment."
	@echo "		! WARNING: This will start and connected to the devcontainer."

setup:
	@echo "Creating Development Environment..."
	@if [[ "$$(pwd)" == *"/frappe-bench"* ]]; then \
		echo "FAIL - Development environment already constructed"; \
		exit 1; \
	fi
	@if [ ! -d ".devcontainers" ]; then \
		echo ".devcontainers folder not found"; \
		exit 1; \
	fi
	@echo "Initializing Dev Container"
	@./development_init.sh

run:
	@echo "Starting Development Environment"
	@./run_dev.sh
