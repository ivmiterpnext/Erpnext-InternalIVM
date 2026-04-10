#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$APP_ROOT/.devcontainer/docker-compose.yml"
PROJECT_NAME="frappe-dev"

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d

echo "Frappe Environment started. Common Commands:"
echo " - bench start"
echo " - bench migrate"
echo " - bench clear-cache"
echo "To leave, type 'exit'"

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -e "TERM=xterm-256color" -w /workspace/frappe-bench frappe bash
