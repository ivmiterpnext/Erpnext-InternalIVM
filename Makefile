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
	@if [ ! -d ".devcontainer" ]; then \
		echo ".devcontainer folder not found"; \
		exit 1; \
	fi
	@echo "Initializing Dev Container"
	@./scripts/setup.sh

run:
	@echo "Starting Development Environment"
	@./scripts/run.sh
