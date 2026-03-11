#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$APP_ROOT/.devcontainer/docker-compose.yml"
PROJECT_NAME="frappe-dev"

if ! docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps | grep -q "frappe"; then
    echo "Error: Development Environment not running."
    echo "Run 'make setup' or 'make run' first."
    exit 1
fi

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T frappe bash -lc "
    cd /workspace/frappe-bench
    bench clear-cache
    bench migrate
    bench clear-cache
    bench restart
    exit
"

echo "Migration complete."
