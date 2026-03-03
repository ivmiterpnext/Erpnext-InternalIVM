#!/bin/bash

echo "Removing old environment"

echo "Clearing Docker Containers"
docker compose -f "$HOME/IVM-Frappe-Bench/.devcontainer/docker-compose.yml" -p frappe-dev down -v

echo "Cleaning Folder Structure"
rm -rf ~/IVM-Frappe-Bench
mkdir -p ~/IVM-Frappe-Bench

echo "Setting up New Environment"
./setup.sh


