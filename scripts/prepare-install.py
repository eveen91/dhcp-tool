#!/usr/bin/env python3
"""Render a private, reviewable LAN installation using already configured credentials."""

import argparse
import ipaddress
import json
import os
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="192.168.1.32")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--allow-cidr", default="192.168.1.0/24")
    args = parser.parse_args()
    host = ipaddress.IPv4Address(args.host)
    network = ipaddress.IPv4Network(args.allow_cidr)
    if not host.is_private or host.is_unspecified or not network.is_private or host not in network:
        parser.error("private_lan_required")
    if not 1024 <= args.port <= 65535:
        parser.error("invalid_port")
    required = ("DJANGO_SECRET_KEY", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    if any(not os.environ.get(name) for name in required):
        parser.error("missing_existing_credentials")
    if (
        os.environ["POSTGRES_DB"].startswith("test_")
        and os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.test"
    ):
        parser.error("test_database_refused")
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.is_symlink() or args.output.stat().st_mode & 0o077:
        parser.error("private_output_directory_required")
    values = {name: os.environ[name] for name in required}
    values.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.lan",
            "DJANGO_ALLOWED_HOSTS": f"{host},127.0.0.1,localhost",
            "DJANGO_CSRF_TRUSTED_ORIGINS": f"http://{host}:{args.port}",
            "POSTGRES_HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "POSTGRES_PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "BACKUP_DOWNLOAD_DIR": "/var/lib/dhcp-tool/backup-download",
            "DHCPD_PARSER_PATH": "/opt/dhcp-tool/bin/dhcpd",
        }
    )
    for name in values:
        if "\n" in values[name] or "\r" in values[name]:
            parser.error("multiline_environment_refused")

    # systemd EnvironmentFile accepts double quotes and escapes; no shell sourcing.
    def write_environment(path, entries):
        if path.is_symlink():
            parser.error("symlink_output_refused")
        path.write_text(
            "".join(
                f'{name}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"\n'
                for name, value in entries.items()
            )
        )
        path.chmod(0o600)

    write_environment(args.output / "backend.env", values)
    write_environment(
        args.output / "frontend.env",
        {
            "DHCP_TOOL_API_URL": "http://127.0.0.1:18000",
            "NEXT_BUILD_DIR": ".next-install",
        },
    )
    root = Path(__file__).resolve().parents[1]
    nginx = (root / "deploy/nginx/lan.conf.template").read_text()
    nginx = (
        nginx.replace("@HOST@", str(host))
        .replace("@PORT@", str(args.port))
        .replace("@CIDR@", str(network))
    )
    (args.output / "nginx.conf").write_text(nginx)
    key = args.output / "export.key"
    if key.is_symlink():
        parser.error("symlink_output_refused")
    if not key.exists():
        key.write_text(secrets.token_urlsafe(48) + "\n")
        key.chmod(0o600)
    print(json.dumps({"event": "installation_prepared", "url": f"http://{host}:{args.port}"}))


if __name__ == "__main__":
    main()
