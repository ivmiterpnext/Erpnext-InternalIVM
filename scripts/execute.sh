#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$APP_ROOT/.devcontainer/docker-compose.yml"
PROJECT_NAME="frappe-dev"

docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T frappe bash -lc "
    cd /workspace/frappe-bench
    bench $@
    exit
"

echo "Executed: bench $@"
