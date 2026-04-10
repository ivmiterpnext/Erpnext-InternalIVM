SHELL := /bin/bash
.DEFAULT_GOAL := help

ifeq ($(firstword $(MAKECMDGOALS)),execute)
EXECUTE_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
$(EXECUTE_ARGS):
	@:
endif

.PHONY: help setup run hard_reset_environment migrate execute

help:
	@echo "Usage:"
	@echo " make setup     : Run first time developer setup"
	@echo " make run       : Start frappe development environment."
	@echo " make hard_reset_environment"
	@echo "                : Hard Reset frappe environment"
	@echo "                  - WARNING: This will not impact changes"
	@echo "                    to the ivm app, but will wipe environment."
	@echo " make migrate   : Run clear-cache, migrate, restart from bench."
	@echo " make execute <bench-args>"
	@echo "                : Run bench with the provided arguments"

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

hard_reset_environment:
	@echo "Refreshing Environment"
	@./scripts/hard_reset_environment.sh
	@./scripts/setup.sh

migrate:
	@./scripts/migrate.sh

execute:
	@./scripts/execute.sh $(EXECUTE_ARGS)
