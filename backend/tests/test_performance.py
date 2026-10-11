"""Reproducible PostgreSQL scale probe; timings are evidence, not a production SLA."""

import json
import os
import platform
import statistics
import time
from ipaddress import IPv4Address
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from dhcp_tool.draft import generator_config, snapshot
from dhcp_tool.generator import render_mvp
from dhcp_tool.history import compare_versions
from dhcp_tool.models import (
    Account,
    Artifact,
    Draft,
    Firewall,
    Pool,
    Reservation,
    Role,
    Subnet,
    Version,
)


@override_settings(DHCPD_PARSER_PATH=None)
class ScaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("scale-admin")
        Account.objects.create(user=cls.user, role=Role.ADMIN)
        firewalls = Firewall.objects.bulk_create(
            [Firewall(name=f"scale-{i:02}", profile="R81.10") for i in range(50)]
        )
        cls.fw = firewalls[0]
        Draft.objects.bulk_create([Draft(firewall=fw) for fw in firewalls])
        cls.draft = Draft.objects.get(firewall=cls.fw)
        subnet = Subnet.objects.create(firewall=cls.fw, name="Scale", cidr="10.20.0.0/16")
        Pool.objects.create(subnet=subnet, start="10.20.200.1", end="10.20.200.100")
        Reservation.objects.bulk_create(
            [
                Reservation(
                    subnet=subnet,
                    name=f"host-{i:05}",
                    ip=str(IPv4Address("10.20.0.10") + i),
                    mac=f"02:00:00:{i >> 16:02x}:{(i >> 8) & 255:02x}:{i & 255:02x}",
                )
                for i in range(5000)
            ]
        )

    def test_scale_response_bounds_query_counts_generation_and_diff(self):
        self.client.force_login(self.user)
        base = f"/api/v1/firewalls/{self.fw.pk}/"
        report = {
            "python": platform.python_version(),
            "firewalls": 50,
            "reservations": 5000,
            "iterations": 5,
            "measurements": {},
        }

        def measure(name, run):
            samples, counts = [], []
            run()  # warm-up excluded
            for _ in range(5):
                with CaptureQueriesContext(connection) as queries:
                    start = time.perf_counter()
                    result = run()
                    samples.append((time.perf_counter() - start) * 1000)
                counts.append(len(queries))
            report["measurements"][name] = {
                "median_ms": round(statistics.median(samples), 2),
                "max_ms": round(max(samples), 2),
                "queries_max": max(counts),
            }
            return result

        def get(path):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            return response

        response = measure("firewall_list", lambda: get("/api/v1/firewalls/"))
        self.assertEqual(len(response.json()["results"]), 50)
        response = measure("reservation_list", lambda: get(base + "reservations/"))
        self.assertEqual(response.json()["count"], 5000)
        self.assertEqual(len(response.json()["results"]), 50)
        response = measure(
            "reservation_search", lambda: get(base + "reservations/?search=host-04999")
        )
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["name"], "host-04999")
        response = measure("draft_snapshot", lambda: get(base + "draft/"))
        self.assertEqual(len(response.json()["subnets"][0]["reservations"]), 5000)
        report["draft_response_bytes"] = len(response.content)
        config = generator_config(self.fw, self.draft)
        content = measure("generator", lambda: render_mvp(config))
        self.assertEqual(content.count(b"fixed-address"), 5000)
        self.assertLess(len(content), 1024 * 1024)
        report["artifact_bytes"] = len(content)
        saved = snapshot(self.fw, self.draft)
        saved["firewall"] = {"name": self.fw.name}
        versions = []
        for n in range(1, 3):
            version = Version.objects.create(
                firewall=self.fw,
                number=n,
                profile="R81.10",
                generator_version="1",
                snapshot=saved,
                author=self.user,
            )
            Artifact.objects.create(version=version, content=content, sha256="a" * 64)
            versions.append(version)
        # Re-read every time to include database fetch/decode costs, not ORM relation caches.
        difference = measure(
            "version_diff",
            lambda: compare_versions(
                Version.objects.get(pk=versions[0].pk), Version.objects.get(pk=versions[1].pk)
            ),
        )
        self.assertEqual(difference, {"text": "", "semantic": []})
        response = measure("version_list", lambda: get(base + "versions/"))
        self.assertEqual(len(response.json()["results"]), 2)
        report["version_list_response_bytes"] = len(response.content)
        for name in (
            "firewall_list",
            "reservation_list",
            "reservation_search",
            "draft_snapshot",
            "version_list",
        ):
            self.assertLessEqual(report["measurements"][name]["queries_max"], 12, name)
        # Query growth must not depend on the number of returned rows.
        with CaptureQueriesContext(connection) as few:
            get(base + "reservations/?page_size=1")
        with CaptureQueriesContext(connection) as many:
            get(base + "reservations/?page_size=100")
        self.assertEqual(len(few), len(many))
        report["reservation_queries_1_vs_100"] = [len(few), len(many)]
        report["search_plan"] = Reservation.objects.filter(
            subnet__firewall=self.fw, name__icontains="host-04999"
        ).explain(analyze=True, buffers=True)
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            report["postgresql"] = cursor.fetchone()[0]
        if output := os.environ.get("DHCP_TOOL_BENCHMARK_REPORT"):
            Path(output).write_text(json.dumps(report, indent=2) + "\n")
