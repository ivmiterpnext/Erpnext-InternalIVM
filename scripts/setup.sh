#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export IVM_FRAPPE_APP_PATH="$APP_ROOT"

mkdir -p "$HOME/IVM-Frappe-Bench"
cp -R .devcontainer "$HOME/IVM-Frappe-Bench"

docker compose -f "$HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml" -p frappe-dev up -d

docker compose -f "$HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml" -p frappe-dev exec -T frappe bash -lc "
    echo 'Initializing frappe development environment...'

    cd /workspace

    bench init --skip-redis-config-generation frappe-bench
    cd frappe-bench

    source env/activate
    pip install azure-identity azure-keyvault-secrets qdrant-client openai

    bench set-config -g db_host mariadb
    bench set-config -g redis_cache redis://redis-cache:6379
    bench set-config -g redis_queue redis://redis-queue:6379
    bench set-config -g redis_socketio redis://redis-queue:6379

    printf '\n' | bench new-site --db-root-password 123 --admin-password admin --mariadb-user-host-login-scope=% ivm.localhost

    bench use ivm.localhost

    bench switch-to-branch v16.9.0 frappe
    bench get-app crm --branch v1.59.0
    bench get-app https://github.com/frappe/wiki
    bench get-app erpnext
    bench install-app crm
    bench install-app wiki
    bench install-app erpnext

    bench get-app --soft-link /workspace/ivm
    bench install-app ivm

    echo 'Dev Container Environment Completed.'
    echo '================================================='
    echo 'Use make run to begin the bench site'
    echo 'Server located at http://ivm.localhost:8000/'
    echo 'Admin Login-  User: administrator, Password: admin'
    echo '================================================='
    echo 'Basic Development Environment Constructed'

    exit
"
