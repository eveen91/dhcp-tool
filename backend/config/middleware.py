import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.cache import patch_vary_headers

from dhcp_tool.auth import api_error

logger = logging.getLogger("dhcp_tool.security")


class NoStoreAPIMiddleware:
    """Never expose debug pages or cache configuration/session responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/v1/"):
            if response.status_code >= 400 and not response.get("Content-Type", "").startswith(
                "application/json"
            ):
                code = {
                    400: "validation_error",
                    403: "permission_denied",
                    404: "not_found",
                    405: "method_not_allowed",
                    413: "request_too_large",
                }.get(response.status_code, "internal_error")
                original = response
                response = api_error(code, "Nie można wykonać żądania.", original.status_code)
                for header in ("Allow", "Retry-After"):
                    if header in original:
                        response[header] = original[header]
            response["Cache-Control"] = "no-store"
            response["Pragma"] = "no-cache"
            patch_vary_headers(response, ["Cookie"])
        return response

    def process_view(self, request, view, args, kwargs):
        if request.path.startswith("/api/v1/"):
            if len(request.META.get("QUERY_STRING", "").encode("utf-8")) > 2048:
                return api_error(
                    "validation_error", "Parametry zapytania przekraczają 2048 bajtów.", 400
                )
            if any(len(request.GET.getlist(key)) != 1 for key in request.GET):
                return api_error("validation_error", "Parametry nie mogą się powtarzać.", 400)
        return None

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/v1/"):
            return None
        if isinstance(exception, Http404):
            return api_error("not_found", "Nie znaleziono zasobu.", 404)
        if isinstance(exception, PermissionDenied):
            return api_error("permission_denied", "Brak uprawnień.", 403)
        logger.error("API failed", extra={"event": "api_error", "status_code": 500})
        return api_error("internal_error", "Nie można wykonać żądania.", 500)
