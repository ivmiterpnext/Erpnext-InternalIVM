#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$APP_ROOT/.devcontainer/docker-compose.yml"
PROJECT_NAME="frappe-dev"

echo "Removing old environment"

echo "Clearing Docker Containers and Volumes..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down -v

echo "Environment reset complete."
echo "Run 'make setup' to recreate the environment."
