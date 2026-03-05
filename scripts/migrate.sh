#!/bin/bash

if [[ ! -d "$HOME/IVM-Frappe-Bench" ]]; then
    echo "Error: Development Environment not configured."
    exit
fi

docker compose -f "$HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml" -p frappe-dev exec -T frappe bash -lc "
    cd /workspace/frappe-bench
    bench clear-cache
    bench migrate
    bench clear-cache
    bench restart
    exit
"

echo "Migration complete."
