#!/usr/bin/env python3
"""Run operator commands with a private single-line EnvironmentFile, without a shell."""

import os
import re
import shlex
import stat
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        raise ValueError("usage")
    path = Path(sys.argv[1])
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ValueError("private_environment_required")
    environment = os.environ.copy()
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError("invalid_environment")
        tokens = shlex.split(value, posix=True)
        if len(tokens) > 1:
            raise ValueError("invalid_environment")
        environment[name] = tokens[0] if tokens else ""
    os.execvpe(sys.argv[2], sys.argv[2:], environment)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError):
        print('{"event":"environment_command_failed"}', file=sys.stderr)
        raise SystemExit(1)
