"""Run the repository proxy template on isolated loopback ports for browser checks."""

import os
import signal
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
# Each suite checks only its own log; do not mix records from earlier runs.
Path("/tmp/dhcp-tool-nginx-e2e-access.log").write_text("")
with tempfile.TemporaryDirectory(prefix="dhcp-tool-nginx-") as temporary:
    directory = Path(temporary)
    if os.environ.get("DHCP_TOOL_E2E_RUNTIME") == "1":
        server = (root / "deploy/nginx/lan.conf.template").read_text()
        server = (
            server.replace("@HOST@", "127.0.0.1")
            .replace("@PORT@", "3102")
            .replace("@CIDR@", "127.0.0.0/8")
        )
        server = server.replace("127.0.0.1:18000", "127.0.0.1:8101").replace(
            "127.0.0.1:13000", "127.0.0.1:3101"
        )
    else:
        server = (root / "docs/nginx-app.conf").read_text()
    server = server.replace("127.0.0.1:8081", "127.0.0.1:3102")
    server = server.replace("127.0.0.1:8000", "127.0.0.1:8101")
    server = server.replace("127.0.0.1:3000", "127.0.0.1:3101")
    server = server.replace(
        "/var/log/nginx/dhcp-tool-access.log", "/tmp/dhcp-tool-nginx-e2e-access.log"
    ).replace("/var/log/dhcp-tool/nginx-access.log", "/tmp/dhcp-tool-nginx-e2e-access.log")
    server = server.replace(
        "    location /api/v1/ {",
        """    location = /nginx-ready/ { return 200 'ready'; }
    location /_next/hmr {
        proxy_pass http://127.0.0.1:3101;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection upgrade;
        proxy_cache off;
    }
    location = /api/v1/test-upstream-outage/ {
        proxy_pass http://127.0.0.1:1;
        proxy_connect_timeout 1s;
        proxy_cache off;
        error_page 502 503 504 =503 @api_unavailable;
    }
    location /api/v1/ {""",
    )
    config = directory / "nginx.conf"
    # Enable cache at the enclosing level to verify that template locations override it.
    config.write_text(f"""daemon off;
worker_processes 1;
pid {directory / "nginx.pid"};
error_log {directory / "error.log"};
events {{ worker_connections 128; }}
http {{
    client_body_temp_path {directory / "body"};
    proxy_temp_path {directory / "proxy"};
    proxy_cache_path {directory / "cache"} keys_zone=review:1m;
    proxy_cache review;
    proxy_cache_valid 200 1m;
    {server}
}}
""")
    subprocess.run(["/usr/sbin/nginx", "-t", "-c", str(config)], check=True)
    process = subprocess.Popen(["/usr/sbin/nginx", "-c", str(config)])

    def stop(signum, frame):
        process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        raise SystemExit(process.wait())
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
