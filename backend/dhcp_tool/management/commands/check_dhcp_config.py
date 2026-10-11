"""Validate JSON configuration without storing or publishing an artifact."""

import hashlib
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dhcp_tool.generator import ConfigurationError, render
from dhcp_tool.syntax import MAX_CONFIG_BYTES, check_syntax


class Command(BaseCommand):
    help = "Validate JSON and optionally check generated ISC DHCP syntax; no Gaia certification."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("input", help="JSON configuration path; never an existing dhcpd.conf")
        parser.add_argument("--parser", default=os.environ.get("DHCPD_PARSER_PATH") or None)
        parser.add_argument("--require-parser", action="store_true")

    def handle(self, *args, **options):
        try:
            with Path(options["input"]).open("rb") as source:
                raw = source.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                raise CommandError("JSON input exceeds the 1 MiB limit")
            artifact = render(json.loads(raw))
            result = check_syntax(artifact, parser_path=options["parser"])
        except (ConfigurationError, OSError, ValueError, RecursionError) as error:
            if isinstance(error, ConfigurationError):
                raise CommandError(str(error)) from None
            raise CommandError(
                "Cannot read or validate JSON; check input and parser configuration"
            ) from None

        report = {
            "data_validated": True,
            "syntax_status": result.status,
            "parser_version": result.parser_version,
            "parser_return_code": result.return_code,
            "gaia_compatibility": "unverified",
            "artifact_bytes": len(artifact),
            "sha256": hashlib.sha256(artifact).hexdigest(),
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if result.status not in {"syntax_checked", "parser_unavailable"}:
            raise CommandError("Syntax verification failed; see syntax_status")
        if options["require_parser"] and result.status != "syntax_checked":
            raise CommandError("A successful parser check is required")
