#!/usr/bin/env bash
set -e

CONTAINER_NAME="frappe-dev"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

mkdir -p temp
for item in * .*; do
    [ "$item" = "." -o "$item" = ".." ] && continue
    if [[ "$item" == "development_init.sh" || "$item" == "frappe-bench" || "$item" == ".devcontainer" || "$item" == "temp" ]]; then
        continue
    fi

    mv -v "$item" temp/
done

rm -rf temp

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

    bench switch-to-branch v16.9.0 frappe
    bench get-app crm --branch v1.59.0
    bench get-app https://github.com/frappe/wiki
    bench get-app erpnext

    bench install-app crm
    bench install-app wiki
    bench install-app erpnext

    bench get-app https://github.com/ivmiterpnext/Erpnext-InternalIVM --branch '$CURRENT_BRANCH'
    bench install-app ivm

    python - <<'PY'
import json
from pathlib import Path

site_config_path = Path("sites/ivm.localhost/site_config.json")

with site_config_path.open("r", encoding="utf-8") as f:
    site_config = json.load(f)

current_value = site_config.get("developer_mode")
is_last_key = list(site_config.keys())[-1] == "developer_mode" if site_config else False

if current_value != 1 or not is_last_key:
    site_config.pop("developer_mode", None)
    site_config["developer_mode"] = 1
    with site_config_path.open("w", encoding="utf-8") as f:
        json.dump(site_config, f, indent=2)
        f.write("\n")
PY

    echo 'Dev Container Environment Completed.'
    echo '================================================='
    echo 'Use cd frappe-bench/apps/ivm to begin development'
    echo 'Use make run to begin the bench site'
    echo 'Server located at http://ivm.localhost:8000/'
    echo 'Admin Login-  User: administrator, Password: admin'
    echo '================================================='

    exit
"
mv development_init.sh frappe-bench/apps/ivm
