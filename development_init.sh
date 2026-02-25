#!/usr/bin/env bash
set -e

CONTAINER_NAME="frappe-dev"

echo "Initializing Container"

docker compose -f .devcontainer/docker-compose.yml -p frappe-dev up -d;
docker exec -it -w /workspace/ $(docker ps --filter "ancestor=frappe/bench:latest" -q) bash -c "
    echo 'Initializing frappe development environment...'

    bench init --skip-redis-config-generation frappe-bench
    cd frappe-bench

    bench set-config -g db_host mariadb
    bench set-config -g redis_cache redis://redis-cache:6379
    bench set-config -g redis_queue redis://redis-queue:6379
    bench set-config -g redis_socketio redis://redis-queue:6379

    bench new-site --db-root-password 123 --admin-password admin --mariadb-user-host-login-scope=% ivm.localhost

    bench use ivm.localhost
    bench get-app frappe --branch v16.9.0
    bench get-app crm --branch v1.59.0
    bench get-app https://github.com/frappe/wiki
    bench get-app erpnext

    bench install-app crm
    bench install-app wiki
    bench install-app erpnext

    exit
"
mkdir -p temp
for item in * .*; do
    [ "$item" = "." -o "$item" = ".." ] && continue
    if [[ "$item" == "development_init.sh" || "$item" == "frappe-bench" || "$item" == ".devcontainer" || "$item" == "temp" ]]; then
        continue
    fi

    mv -v "$item" temp/
done

mv temp ivm
mv ivm frappe-bench/apps
docker exec -it -w /workspace/ $(docker ps --filter "ancestor=frappe/bench:latest" -q) bash -c "bench install-app ivm && exit"

echo 'Dev Container Environment Completed.'
echo 'Server located at http://ivm.localhost:8000/'
echo 'Admin Login-  User: administrator, Password: admin.'
