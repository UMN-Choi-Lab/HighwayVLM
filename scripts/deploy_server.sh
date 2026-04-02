#!/usr/bin/env bash
set -euo pipefail

# One-command server deploy for HighwayVLM.
# Usage:
#   bash scripts/deploy_server.sh
# Optional env overrides:
#   REPO_DIR=$HOME/HighwayVLM
#   REPO_URL=https://github.com/UMN-Choi-Lab/HighwayVLM.git
#   BRANCH=main
#   COMPOSE_FILE=infra/docker/docker-compose.server.yml
#   SERVICE_NAME=highwayvlm

REPO_DIR="${REPO_DIR:-$HOME/HighwayVLM}"
REPO_URL="${REPO_URL:-https://github.com/UMN-Choi-Lab/HighwayVLM.git}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/docker-compose.server.yml}"
SERVICE_NAME="${SERVICE_NAME:-highwayvlm}"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "[deploy] Cloning repo into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

echo "[deploy] Updating branch $BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
else
  DC=(docker-compose)
fi

echo "[deploy] Rebuilding and recreating container"
"${DC[@]}" -f "$COMPOSE_FILE" up -d --build --force-recreate

echo "[deploy] Container status"
docker ps --filter "name=^${SERVICE_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo "[deploy] Health check"
curl -fsS http://127.0.0.1:3000/health
echo

echo "[deploy] Recent archive files (if any)"
if [[ -d /data2/HighwayVLM ]]; then
  find /data2/HighwayVLM -type f | head -20 || true
else
  echo "/data2/HighwayVLM does not exist yet."
fi

echo "[deploy] Done"
