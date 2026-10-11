import unittest

from dhcp_tool.generator import ConfigurationError, render


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "firewall": "fw-warszawa",
            "profile": "R81.10",
            "default_lease_time": 3600,
            "max_lease_time": 7200,
            "dns": ["1.1.1.1", "8.8.8.8"],
            "domain": "example.org",
            "subnets": [
                {
                    "cidr": "192.0.2.0/24",
                    "gateway": "192.0.2.1",
                    "interface_address": "192.0.2.2",
                    "pools": [{"start": "192.0.2.100", "end": "192.0.2.150"}],
                    "reservations": [
                        {"id": "printer-1", "mac": "AA-BB-CC-00-00-01", "ip": "192.0.2.20"}
                    ],
                }
            ],
        }

    def test_renders_complete_deterministic_file(self):
        self.assertEqual(
            render(self.config),
            (
                "# Generated DHCPv4 configuration for fw-warszawa (Gaia R81.10)\n"
                "# Do not edit this artifact; changes belong in the configuration editor.\n"
                "\n"
                "ddns-update-style none;\n"
                "\n"
                "default-lease-time 3600;\n"
                "max-lease-time 7200;\n"
                'option domain-name "example.org";\n'
                "option domain-name-servers 1.1.1.1, 8.8.8.8;\n"
                "\n"
                "subnet 192.0.2.0 netmask 255.255.255.0 {\n"
                "  option routers 192.0.2.1;\n"
                "  range 192.0.2.100 192.0.2.150;\n"
                "}\n"
                "\n"
                "host printer-1 {\n"
                "  hardware ethernet aa:bb:cc:00:00:01;\n"
                "  fixed-address 192.0.2.20;\n"
                "}\n"
            ).encode("ascii"),
        )

    def test_emits_checked_gaia_host_name_expression_only_when_enabled(self):
        self.config["subnets"][0]["gaia_host_name_fallback"] = True
        result = render(self.config).decode("ascii")
        self.assertIn(
            '  option host-name = pick(option host-name,\n    concat("dhcp-", binary-to-ascii(10, 8, "-", leased-address)));\n',
            result,
        )
        self.assertNotIn(
            "option host-name =",
            render(
                {
                    **self.config,
                    "subnets": [{**self.config["subnets"][0], "gaia_host_name_fallback": False}],
                }
            ).decode("ascii"),
        )

    def test_gaia_reference_layout_directives_are_preserved(self):
        """Check Point sample: lease times, host-name fallback, range, router and DNS per subnet."""
        config = {
            "firewall": "reference-fw",
            "profile": "R81.10",
            "subnets": [
                {
                    "cidr": cidr,
                    "default_lease_time": 43200,
                    "max_lease_time": 86400,
                    "gaia_host_name_fallback": True,
                    "gateway": gateway,
                    "dns": ["8.8.8.8"],
                    "pools": [{"start": start, "end": end}],
                }
                for cidr, start, end, gateway in (
                    ("10.44.91.0/25", "10.44.91.10", "10.44.91.120", "10.44.91.1"),
                    ("10.44.32.0/24", "10.44.32.10", "10.44.32.250", "10.44.32.1"),
                )
            ],
        }
        result = render(config).decode("ascii")
        self.assertEqual(result.count("ddns-update-style none;"), 1)
        self.assertEqual(result.count("default-lease-time 43200;"), 2)
        self.assertEqual(result.count("max-lease-time 86400;"), 2)
        self.assertEqual(result.count("option host-name = pick(option host-name,"), 2)
        self.assertEqual(result.count("option domain-name-servers 8.8.8.8;"), 2)
        self.assertIn("subnet 10.44.91.0 netmask 255.255.255.128 {", result)
        self.assertIn("range 10.44.91.10 10.44.91.120;", result)
        self.assertIn("option routers 10.44.91.1;", result)
        self.assertIn("subnet 10.44.32.0 netmask 255.255.255.0 {", result)
        self.assertIn("range 10.44.32.10 10.44.32.250;", result)
        self.assertIn("option routers 10.44.32.1;", result)
        self.assertLess(result.index("subnet 10.44.32.0"), result.index("subnet 10.44.91.0"))

    def test_sorts_and_omits_inactive_items(self):
        self.config["subnets"][0]["pools"] = [
            {"start": "192.0.2.180", "end": "192.0.2.190"},
            {"start": "192.0.2.20", "end": "192.0.2.30", "active": False},
            {"start": "192.0.2.100", "end": "192.0.2.150"},
        ]
        self.config["subnets"][0]["reservations"] = []
        self.config["subnets"].append(
            {
                "cidr": "198.51.100.0/24",
                "active": False,
                "pools": [{"start": "198.51.100.10", "end": "198.51.100.20"}],
            }
        )
        result = render(self.config).decode("ascii")
        self.assertLess(result.index("range 192.0.2.100"), result.index("range 192.0.2.180"))
        self.assertNotIn("198.51.100", result)
        self.assertNotIn("range 192.0.2.20", result)

    def test_rejects_overlapping_pool_and_reservation(self):
        self.config["subnets"][0]["reservations"][0]["ip"] = "192.0.2.100"
        with self.assertRaisesRegex(ConfigurationError, "reservations.*ip"):
            render(self.config)

    def test_rejects_directive_injection(self):
        for field, value in [
            ("firewall", 'fw\ninclude "evil";'),
            ("domain", 'example.org";\noption routers 1.2.3.4;'),
        ]:
            with self.subTest(field=field):
                config = {**self.config, field: value}
                with self.assertRaises(ConfigurationError):
                    render(config)

    def test_rejects_unsupported_profile(self):
        with self.assertRaises(ConfigurationError):
            render({**self.config, "profile": "R99"})

    def test_rejects_non_string_addresses_and_profile(self):
        with self.assertRaises(ConfigurationError):
            render({**self.config, "profile": []})
        self.config["subnets"][0]["reservations"][0]["ip"] = 3221226004
        with self.assertRaises(ConfigurationError):
            render(self.config)

    def test_rejects_invalid_lease_order(self):
        with self.assertRaisesRegex(ConfigurationError, "lease"):
            render({**self.config, "default_lease_time": 9000})

    def test_reservation_only_subnet(self):
        self.config["profile"] = "R82.10"
        self.config["subnets"][0]["pools"] = []
        result = render(self.config).decode("ascii")
        self.assertIn("subnet 192.0.2.0 netmask 255.255.255.0 {", result)
        self.assertIn("host printer-1 {", result)
        self.assertNotIn("range ", result)

    def test_rejects_network_broadcast_gateway_and_interface_in_pool(self):
        for start, end in [
            ("192.0.2.0", "192.0.2.10"),
            ("192.0.2.200", "192.0.2.255"),
            ("192.0.2.1", "192.0.2.10"),
            ("192.0.2.2", "192.0.2.10"),
        ]:
            with self.subTest(start=start):
                self.config["subnets"][0]["pools"] = [{"start": start, "end": end}]
                with self.assertRaisesRegex(ConfigurationError, "pools"):
                    render(self.config)

    def test_rejects_overlapping_subnets_and_duplicate_mac(self):
        self.config["subnets"].append({"cidr": "192.0.2.0/25"})
        with self.assertRaisesRegex(ConfigurationError, "overlapping"):
            render(self.config)
        self.config["subnets"].pop()
        self.config["subnets"].append(
            {
                "cidr": "198.51.100.0/24",
                "reservations": [
                    {"id": "printer-2", "ip": "198.51.100.20", "mac": "aa:bb:cc:00:00:01"}
                ],
            }
        )
        with self.assertRaisesRegex(ConfigurationError, "duplicate MAC"):
            render(self.config)

    def test_subnet_overrides_global_dns_and_lease(self):
        self.config["subnets"][0].update({"dns": ["9.9.9.9"], "default_lease_time": 1200})
        result = render(self.config).decode("ascii")
        self.assertIn("default-lease-time 3600;", result)
        self.assertIn("  default-lease-time 1200;", result)
        self.assertIn("  option domain-name-servers 9.9.9.9;", result)

    def test_rejects_unsupported_and_malformed_fields(self):
        for change in (
            {"extra_directives": "allow unknown-clients;"},
            {"subnets": [{**self.config["subnets"][0], "raw": "deny all;"}]},
            {"subnets": [{**self.config["subnets"][0], "pools": "oops"}]},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ConfigurationError):
                    render({**self.config, **change})

    def test_empty_config_is_blocked(self):
        self.config["subnets"] = []
        with self.assertRaisesRegex(ConfigurationError, "subnets"):
            render(self.config)


if __name__ == "__main__":
    unittest.main()
