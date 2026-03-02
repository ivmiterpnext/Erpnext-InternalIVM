#!/usr/bin/env bash
set -e

docker compose -f ../../../.devcontainer/docker-compose.yml -p frappe-dev up -d;
echo "Frappe Environment started. Common Commands:"
echo " - bench start"
echo " - bench migrate"
echo " - bench clear-cache"
echo "To leave, type 'exit'"
docker exec -it -e "TERM=xterm-256color" -w /workspace/frappe-bench $(docker ps --filter "ancestor=frappe/bench:latest" -q) bash
