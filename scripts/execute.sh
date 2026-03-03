#!/bin/bash

docker compose -f "$HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml" -p frappe-dev exec -T frappe bash -lc "
    cd /workspace/frappe-bench
    bench $@
    exit
"

echo "Executed: bench $@"
