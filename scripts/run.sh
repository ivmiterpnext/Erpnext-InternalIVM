#!/bin/bash

# docker exec -it -e "TERM=xterm-256color" -w /workspace/frappe-bench $(docker ps --filter "ancestor=frappe/bench:latest" -q) bash
docker compose -f $HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml -p frappe-dev up -d;
echo "Frappe Environment started. Common Commands:"
echo " - bench start"
echo " - bench migrate"
echo " - bench clear-cache"
echo "To leave, type 'exit'"
docker compose -f $HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml -p frappe-dev exec -e "TERM=xterm-256color" -w /workspace/frappe-bench frappe bash
