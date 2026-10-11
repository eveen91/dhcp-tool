#!/usr/bin/env bash
set -euo pipefail
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/dhcp-tool-uv-cache}"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
(
  cd backend
  uv run --offline --no-sync ruff check . ../scripts/publish-backup.py ../scripts/operations.py ../scripts/prepare-install.py ../scripts/run-with-env.py ../scripts/e2e-nginx.py ../deploy/gunicorn.conf.py
  uv run --offline --no-sync ruff format --check . ../scripts/publish-backup.py ../scripts/operations.py ../scripts/prepare-install.py ../scripts/run-with-env.py ../scripts/e2e-nginx.py ../deploy/gunicorn.conf.py
  uv run --offline --no-sync --env-file .env.test python manage.py check
  uv run --offline --no-sync --env-file .env.test pytest
)
(
  cd frontend
  npm run format:check
  npm run lint
  npm run api:check
  npm run typecheck
  npm test
  DHCP_TOOL_API_URL=http://127.0.0.1:8101 NEXT_BUILD_DIR=.next-quality NEXT_TELEMETRY_DISABLED=1 npm run build
  DHCP_TOOL_E2E_PRODUCTION=1 DHCP_TOOL_E2E_RUNTIME=1 npm run test:e2e
)
