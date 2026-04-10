#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$APP_ROOT/.devcontainer/docker-compose.yml"
PROJECT_NAME="frappe-dev"

echo "Starting containers..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d

echo "Initializing frappe development environment..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T frappe bash -lc '
    set -euo pipefail

    BENCH_DIR="/workspace/frappe-bench"

    # Fix ownership of named volume mount (created as root by Docker)
    sudo chown -R frappe:frappe "$BENCH_DIR"

    # Idempotent bench init: check for a valid bench marker
    if [ ! -f "$BENCH_DIR/sites/common_site_config.json" ]; then
        echo "Initializing frappe bench..."
        cd /workspace
        bench init --ignore-exist --skip-redis-config-generation --frappe-branch version-16 frappe-bench
    else
        echo "Bench already initialized, skipping init."
    fi

    cd "$BENCH_DIR"
    source env/bin/activate
    pip install azure-identity azure-keyvault-secrets

    # Configure services (idempotent — set-config overwrites)
    bench set-config -g db_host mariadb
    bench set-config -g redis_cache redis://redis-cache:6379
    bench set-config -g redis_queue redis://redis-queue:6379
    bench set-config -g redis_socketio redis://redis-queue:6379

    # Create site if not present
    if [ ! -d "sites/ivm.localhost" ]; then
        echo "Creating site ivm.localhost..."
        printf "\n" | bench new-site --db-root-password 123 --admin-password admin \
            --mariadb-user-host-login-scope=% ivm.localhost
    else
        echo "Site ivm.localhost already exists, skipping."
    fi

    bench use ivm.localhost
    bench set-config developer_mode 1

    if [ -n "${HUBSPOT_API_KEY:-}" ]; then
        bench set-config hubspot_api_key "${HUBSPOT_API_KEY}"
    else
        echo "No Hubspot API Key"
    fi
    if [ -n "${HUBSPOT_CLIENT_SECRET:-}" ]; then
        bench set-config hubspot_client_secret "${HUBSPOT_CLIENT_SECRET}"
    else
        echo "No Hubspot Client Secret"
    fi

    if [ ! -d "apps/crm" ]; then
        echo "Installing crm..."
        bench get-app crm --branch v1.59.0
        bench install-app crm
    else
        echo "crm already installed, skipping."
    fi

    if [ ! -d "apps/wiki" ]; then
        echo "Installing wiki..."
        bench get-app https://github.com/frappe/wiki
        bench install-app wiki
    else
        echo "wiki already installed, skipping."
    fi

    if [ ! -d "apps/erpnext" ]; then
        echo "Installing erpnext..."
        bench get-app erpnext
        bench install-app erpnext
    else
        echo "erpnext already installed, skipping."
    fi

    if [ ! -L "apps/ivm" ] && [ ! -d "apps/ivm" ]; then
        echo "Linking ivm app..."
        bench get-app --soft-link /workspace/ivm
        bench install-app ivm
    else
        echo "ivm app already linked, skipping."
    fi

    echo "Running migrations..."
    bench clear-cache
    bench migrate
    bench restart

    echo "================================================="
    echo "Dev Container Environment Completed."
    echo "Use make run to begin the bench site"
    echo "Server located at http://ivm.localhost:8000/"
    echo "Admin Login - User: administrator, Password: admin"
    echo "================================================="
    echo "Basic Development Environment Constructed"
'
