#!/usr/bin/env bash
set -e

cd ../../../ && docker compose -f .devcontainer/docker-compose.yml -p frappe-dev up -d;
docker exec -it -w /workspace/ \ $(docker ps --filter "ancestor=frappe/bench:latest" -q) bash
cd frappe-bench/

echo "Frappe Environment Entered. Common Commands:"
echo " - bench start"
echo " - bench migrate"
echo " - bench clear-cache"
