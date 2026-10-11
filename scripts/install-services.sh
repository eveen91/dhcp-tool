#!/usr/bin/env bash
# Install only after reviewing the generated .deployment configuration.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo 'Run this script with sudo; it installs system accounts, releases and services.' >&2
  exit 1
fi
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
configuration="${1:-$source_root/.deployment}"
parser_source="${2:-/opt/dhcp-tool/bin/dhcpd}"
if [[ ! -x "$parser_source" && $# -lt 2 ]]; then
  parser_source=/tmp/dhcp-tool-parser/extracted/usr/sbin/dhcpd
fi
uv_binary="${3:-/home/seba/.local/bin/uv}"
for file in backend.env frontend.env nginx.conf export.key; do
  [[ -f "$configuration/$file" && ! -L "$configuration/$file" ]] || { echo 'Missing reviewed configuration.' >&2; exit 1; }
done
[[ -x "$parser_source" && -x "$uv_binary" ]] || { echo 'Parser or uv executable missing.' >&2; exit 1; }
[[ -f "$source_root/frontend/.next-install/BUILD_ID" ]] || { echo 'Prepare the .next-install production build first.' >&2; exit 1; }
command -v gpg >/dev/null
command -v pg_dump >/dev/null
[[ -x /usr/sbin/logrotate ]]
[[ "$(/usr/bin/node -p 'process.versions.node.split(".")[0]')" = 24 ]] || { echo 'Node.js 24 required.' >&2; exit 1; }
release="/opt/dhcp-tool/releases/$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$release" ]] || { echo 'Release directory already exists.' >&2; exit 1; }
install -d -m 0755 /opt/dhcp-tool/releases /opt/dhcp-tool/bin "$release"
# Only deploy application code, locked dependencies and operator procedures.
tar -C "$source_root" --exclude=backend/.venv --exclude=backend/.env --exclude='backend/.env.*' --exclude=backend/.local-postgres.sql --exclude=backend/.pytest_cache --exclude=backend/.ruff_cache --exclude='*/__pycache__' --exclude=frontend/.next --exclude=frontend/.next-quality --exclude=frontend/.next-e2e --exclude=frontend/test-results --exclude=frontend/playwright-report --exclude=frontend/node_modules --exclude='frontend/.env*' -cf - backend frontend scripts deploy docs | tar -C "$release" -xf -
cp -a "$source_root/frontend/node_modules" "$release/frontend/node_modules"
# New venv at its final path: moving an existing venv breaks executable shebangs.
(cd "$release/backend" && "$uv_binary" sync --frozen --no-dev --python /usr/bin/python3.13 --no-managed-python --no-python-downloads --cache-dir /var/cache/dhcp-tool-uv)
chown -R root:root "$release"
chmod -R go-w "$release"
for account in dhcp-api dhcp-web; do
  if ! getent passwd "$account" >/dev/null; then
    useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$account"
  fi
done
install -d -m 0700 /etc/dhcp-tool /var/backups/dhcp-tool
install -d -m 0750 -o root -g dhcp-api /var/lib/dhcp-tool/backup-download
if [[ -f /etc/dhcp-tool/backend.env ]]; then
  cp -p /etc/dhcp-tool/backend.env /etc/dhcp-tool/previous-backend.env
fi
if [[ -f /etc/dhcp-tool/frontend.env ]]; then
  cp -p /etc/dhcp-tool/frontend.env /etc/dhcp-tool/previous-frontend.env
fi
install -m 0600 "$configuration/backend.env" /etc/dhcp-tool/backend.env
install -m 0600 "$configuration/frontend.env" /etc/dhcp-tool/frontend.env
# Keep the encryption key OUTSIDE the configuration archive; do not rotate it on update.
if [[ ! -e /etc/dhcp-tool-backup.key ]]; then
  install -m 0600 "$configuration/export.key" /etc/dhcp-tool-backup.key
fi
if [[ "$(readlink -f -- "$parser_source")" != /opt/dhcp-tool/bin/dhcpd ]]; then
  install -m 0755 "$parser_source" /opt/dhcp-tool/bin/dhcpd
fi
install -d -o dhcp-web -g dhcp-web -m 0700 "$release/frontend/.next-install/cache"
chown -R dhcp-web:dhcp-web "$release/frontend/.next-install/cache"
install -m 0644 "$release/deploy/systemd/"* /etc/systemd/system/
install -m 0644 "$release/deploy/logrotate.conf" /etc/logrotate.d/dhcp-tool
install -d -m 0750 -g adm /var/log/dhcp-tool
install -d -m 0755 /etc/systemd/journald.conf.d
install -m 0644 "$release/deploy/journald.conf" /etc/systemd/journald.conf.d/dhcp-tool.conf
systemctl restart systemd-journald
# Snapshot the operational configuration together with DB exports.
install -d -m 0700 /etc/dhcp-tool/service-config
cp "$release/deploy/systemd/"* "$release/deploy/gunicorn.conf.py" "$release/deploy/logrotate.conf" "$release/deploy/journald.conf" /etc/dhcp-tool/service-config/
install -m 0600 "$configuration/nginx.conf" /etc/dhcp-tool/service-config/nginx.conf
printf '%s\n' "$release" > /etc/dhcp-tool/release.txt
# Export before migrations; fail before changing the database if export fails.
/usr/bin/python3 "$release/scripts/run-with-env.py" /etc/dhcp-tool/backend.env "$release/backend/.venv/bin/python" "$release/scripts/operations.py" export --config-dir /etc/dhcp-tool --output-dir /var/backups/dhcp-tool --key-file /etc/dhcp-tool-backup.key
# Validate settings with the service environment without exposing or sourcing secrets.
/usr/bin/python3 "$release/scripts/run-with-env.py" /etc/dhcp-tool/backend.env "$release/backend/.venv/bin/python" "$release/backend/manage.py" check
/usr/bin/python3 "$release/scripts/run-with-env.py" /etc/dhcp-tool/backend.env "$release/backend/.venv/bin/python" "$release/backend/manage.py" migrate --noinput
# Preserve the old release and temporary status proxy for an operator rollback.
if [[ -L /opt/dhcp-tool/current ]]; then
  readlink -f /opt/dhcp-tool/current > /etc/dhcp-tool/previous-release.txt
fi
ln -s "$release" /opt/dhcp-tool/current.new
mv -Tf /opt/dhcp-tool/current.new /opt/dhcp-tool/current
if [[ -f /etc/nginx/conf.d/dhcp-tool-status.conf ]]; then
  mv /etc/nginx/conf.d/dhcp-tool-status.conf /etc/dhcp-tool/previous-status.conf
fi
if [[ -f /etc/nginx/conf.d/dhcp-tool.conf ]]; then
  cp /etc/nginx/conf.d/dhcp-tool.conf /etc/dhcp-tool/previous-nginx.conf
fi
install -m 0644 "$configuration/nginx.conf" /etc/nginx/conf.d/dhcp-tool.conf
if ! /usr/sbin/nginx -t; then
  if [[ -f /etc/dhcp-tool/previous-nginx.conf ]]; then
    cp /etc/dhcp-tool/previous-nginx.conf /etc/nginx/conf.d/dhcp-tool.conf
  else
    mv /etc/nginx/conf.d/dhcp-tool.conf /etc/dhcp-tool/rejected-nginx.conf
  fi
  if [[ -f /etc/dhcp-tool/previous-status.conf ]]; then
    mv /etc/dhcp-tool/previous-status.conf /etc/nginx/conf.d/dhcp-tool-status.conf
  fi
  echo 'Nginx configuration rejected; previous proxy restored. Application migrations may already be applied.' >&2
  exit 1
fi
install -d -m 0755 /etc/systemd/system/nginx.service.d
install -m 0644 "$release/deploy/nginx-systemd/dhcp-tool.conf" /etc/systemd/system/nginx.service.d/dhcp-tool.conf
install -m 0600 "$release/deploy/nginx-systemd/dhcp-tool.conf" /etc/dhcp-tool/service-config/nginx-systemd.conf
systemctl daemon-reload
systemctl enable --now dhcp-tool-api.service dhcp-tool-web.service
systemctl restart dhcp-tool-api.service dhcp-tool-web.service
systemctl restart nginx
systemctl start dhcp-tool-backup.service
systemctl enable --now dhcp-tool-backup.timer dhcp-tool-monitor.timer
systemctl start dhcp-tool-monitor.service
systemctl is-active dhcp-tool-api.service dhcp-tool-web.service nginx
printf '%s\n' 'Installed. Keep the export key offline, verify the panel and follow the reboot checklist.'
