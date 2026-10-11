import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError

from dhcp_tool.generator import ConfigurationError


class SyntaxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def parser(self, body):
        executable = self.root / "parser with spaces"
        executable.write_text(f"#!{sys.executable}\n" + body)
        executable.chmod(0o700)
        return str(executable)

    def check(self, content=b"ddns-update-style none;\n", **kwargs):
        # Import inside the test so missing implementation fails each behavior,
        # rather than stopping collection of the existing suite.
        from dhcp_tool.syntax import check_syntax

        return check_syntax(content, **kwargs)

    def test_missing_parser_never_claims_checked_syntax(self):
        result = self.check(parser_path=str(self.root / "missing"))
        self.assertEqual(result.status, "parser_unavailable")
        self.assertIsNone(result.parser_version)

    def test_parser_checks_exact_bytes_without_shell_and_cleans_temp_files(self):
        record = self.root / "record.json"
        parser = self.parser(
            "import json, sys\nfrom pathlib import Path\n"
            'if sys.argv[1:] == ["--version"]:\n'
            '    print("isc-dhcpd-4.4.3-P1"); sys.exit(0)\n'
            'assert sys.argv[1:4] == ["-t", "-4", "-cf"]\n'
            'assert sys.argv[5] == "-lf" and sys.argv[7] == "-pf"\n'
            "config = Path(sys.argv[4])\n"
            f"Path({str(record)!r}).write_text(json.dumps("
            '{"path": str(config), "bytes": config.read_bytes().hex()}))\n'
            "assert config.stat().st_mode & 0o777 == 0o600\n"
        )
        result = self.check(parser_path=parser)
        self.assertEqual(result.status, "syntax_checked")
        self.assertEqual(result.parser_version, "isc-dhcpd-4.4.3-P1")
        data = json.loads(record.read_text())
        self.assertEqual(bytes.fromhex(data["bytes"]), b"ddns-update-style none;\n")
        self.assertFalse(Path(data["path"]).exists())

    def test_rejected_syntax_is_distinct_from_missing_parser(self):
        parser = self.parser(
            "import sys\n"
            'if sys.argv[1:] == ["--version"]:\n'
            '    print("isc-dhcpd-4.4.3-P1"); sys.exit(0)\n'
            "sys.exit(1)\n"
        )
        self.assertEqual(self.check(parser_path=parser).status, "syntax_error")

    def test_crashed_parser_is_not_reported_as_syntax_error(self):
        parser = self.parser(
            "import os, signal, sys\n"
            'if sys.argv[1:] == ["--version"]:\n'
            '    print("isc-dhcpd-4.4.3-P1"); sys.exit(0)\n'
            "os.kill(os.getpid(), signal.SIGKILL)\n"
        )
        self.assertEqual(self.check(parser_path=parser).status, "parser_error")

    def test_parser_timeout_is_bounded(self):
        parser = self.parser("import time\ntime.sleep(10)\n")
        self.assertEqual(self.check(parser_path=parser, timeout=0.1).status, "parser_timeout")

    def test_excessive_parser_output_is_stopped(self):
        parser = self.parser('import sys\nsys.stdout.write("x" * 100000)\n')
        self.assertEqual(self.check(parser_path=parser).status, "parser_error")

    def test_non_executable_parser_is_unavailable(self):
        path = self.root / "not-executable"
        path.write_text("not a parser")
        self.assertEqual(self.check(parser_path=str(path)).status, "parser_unavailable")

    def test_oversized_configuration_is_rejected_before_execution(self):
        with self.assertRaises(ConfigurationError):
            self.check(b"x" * 11, max_bytes=10, parser_path=str(self.root / "missing"))

    def test_relative_parser_path_is_not_executed(self):
        with self.assertRaises(ValueError):
            self.check(parser_path="dhcpd")


class CheckConfigurationCommandTests(unittest.TestCase):
    def test_command_rejects_non_object_subnets_as_validation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.json"
            for invalid in (None, "not-an-object", 42, []):
                with self.subTest(subnet=invalid):
                    source.write_text(
                        json.dumps(
                            {
                                "firewall": "fw-test",
                                "profile": "R81.10",
                                "subnets": [invalid],
                            }
                        )
                    )
                    with self.assertRaisesRegex(CommandError, "subnets"):
                        call_command("check_dhcp_config", str(source), stdout=StringIO())

    def test_command_reports_data_validation_and_unverified_gaia(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(
                json.dumps(
                    {
                        "firewall": "fw-test",
                        "profile": "R81.10",
                        "subnets": [{"cidr": "192.0.2.0/24"}],
                    }
                )
            )
            output = StringIO()
            call_command(
                "check_dhcp_config",
                str(source),
                parser=str(source.parent / "missing"),
                stdout=output,
            )
            result = json.loads(output.getvalue())
            self.assertTrue(result["data_validated"])
            self.assertEqual(result["syntax_status"], "parser_unavailable")
            self.assertEqual(result["gaia_compatibility"], "unverified")
            with self.assertRaises(CommandError):
                call_command(
                    "check_dhcp_config",
                    str(source),
                    parser=str(source.parent / "missing"),
                    require_parser=True,
                    stdout=StringIO(),
                )

    def test_command_rejects_invalid_data_before_parser_check(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.json"
            source.write_text('{"firewall": "fw-test", "profile": "R81.10", "subnets": []}')
            with self.assertRaisesRegex(CommandError, "subnets"):
                call_command("check_dhcp_config", str(source), stdout=StringIO())


@unittest.skipUnless(os.environ.get("DHCPD_PARSER_PATH"), "No real ISC parser configured")
class RealParserTests(unittest.TestCase):
    def test_real_parser_checks_generated_options_pools_and_reservation_only_subnet(self):
        from dhcp_tool.generator import render
        from dhcp_tool.syntax import check_syntax

        example = Path(__file__).resolve().parents[2] / "docs/examples/dhcp-config.json"
        config = json.loads(example.read_text())
        for profile in ("R81.10", "R82.10"):
            with self.subTest(profile=profile):
                config["profile"] = profile
                result = check_syntax(render(config), parser_path=os.environ["DHCPD_PARSER_PATH"])
                self.assertEqual(result.status, "syntax_checked")
                self.assertIsNotNone(result.parser_version)

    def test_real_parser_rejects_invalid_syntax(self):
        from dhcp_tool.syntax import check_syntax

        result = check_syntax(b"subnet broken {\n", parser_path=os.environ["DHCPD_PARSER_PATH"])
        self.assertEqual(result.status, "syntax_error")
