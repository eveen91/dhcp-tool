"""Download only the root-published encrypted export, never its encryption key."""

import json
import os
import re
import stat
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from django.views.decorators.http import require_GET

from dhcp_tool.auth import api_error, role_for
from dhcp_tool.models import Role


@require_GET
def latest_backup(request):
    if role_for(request.user) != Role.ADMIN:
        return api_error("forbidden", "Wymagane konto administratora.", 403)
    if request.GET:
        return api_error("validation_error", "Pobieranie nie przyjmuje parametrów.", 400)
    stream = None
    try:
        configured = settings.BACKUP_DOWNLOAD_DIR
        if not configured:
            raise ValueError
        root = Path(configured).resolve(strict=True)
        directory = (root / "current").resolve(strict=True)
        if directory == root or not directory.is_relative_to(root):
            raise ValueError
        descriptor = os.open(directory / "metadata.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as metadata_file:
            if not stat.S_ISREG(os.fstat(metadata_file.fileno()).st_mode):
                raise ValueError
            metadata = json.loads(metadata_file.read(4097))
        filename = metadata["filename"]
        checksum = metadata["sha256"]
        if not re.fullmatch(r"dhcp-tool-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gpg", filename):
            raise ValueError
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError
        descriptor = os.open(directory / "artifact.tar.gpg", os.O_RDONLY | os.O_NOFOLLOW)
        stream = os.fdopen(descriptor, "rb")
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != metadata["size"]:
            raise ValueError
        response = FileResponse(
            stream, as_attachment=True, filename=filename, content_type="application/octet-stream"
        )
        response["X-Backup-SHA256"] = checksum
        return response
    except (OSError, ValueError, KeyError, TypeError):
        if stream is not None:
            stream.close()
        return api_error("backup_unavailable", "Backup nie jest jeszcze dostępny.", 404)
