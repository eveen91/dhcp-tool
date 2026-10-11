"""Prepare a complete MVP artifact and a bounded syntax report without storage."""

import hashlib
import uuid

from .generator import render_mvp
from .syntax import check_syntax


def prepare_artifact(config, *, parser_path=None, version_id=None):
    content = render_mvp(config)
    if version_id is not None:
        identifier = uuid.UUID(str(version_id))
        content = f"# Published version: {identifier}\n".encode("ascii") + content
    result = check_syntax(content, parser_path=parser_path)
    report = {
        "data_validated": True,
        "syntax_status": result.status,
        "parser_version": result.parser_version,
        "parser_return_code": result.return_code,
        "gaia_compatibility": "unverified",
        "artifact_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    return content, report
