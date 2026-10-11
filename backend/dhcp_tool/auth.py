"""Session login with explicit CSRF and a shared, atomic PostgreSQL limiter."""

import json
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .models import Account, LoginBucket, Role

logger = logging.getLogger("dhcp_tool.security")


def api_error(code, message, status, *, fields=None):
    return JsonResponse(
        {"error": {"code": code, "message": message, "fields": fields or {}}}, status=status
    )


def csrf_failure(request, reason=""):
    return api_error("csrf_failed", "Wymagany poprawny token CSRF.", 403)


def role_for(user):
    if not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return Role.ADMIN
    return Account.objects.filter(user=user).values_list("role", flat=True).first()


def session_data(request):
    user = request.user
    return {
        "user": {"id": user.pk, "username": user.username, "role": role_for(user)}
        if user.is_authenticated
        else None,
        "csrf_token": get_token(request),
    }


def reserve_attempt(username, address):
    now = timezone.now()
    expires = now + timedelta(seconds=settings.LOGIN_WINDOW_SECONDS)
    buckets = [
        (salted_hmac("login-ip", address, algorithm="sha256").hexdigest(), settings.LOGIN_IP_LIMIT),
        (
            salted_hmac("login-account", username.casefold(), algorithm="sha256").hexdigest(),
            settings.LOGIN_ACCOUNT_LIMIT,
        ),
    ]
    # Lock IP then account in every worker. Blocked IPs never allocate new account rows.
    # Password hashing happens after the transaction, outside these short-lived locks.
    with transaction.atomic():
        for key, limit in buckets:
            LoginBucket.objects.get_or_create(key=key, defaults={"expires_at": expires})
            bucket = LoginBucket.objects.select_for_update().get(pk=key)
            if bucket.expires_at <= now:
                bucket.attempts = 0
                bucket.expires_at = expires
            if bucket.attempts >= limit:
                return max(1, math.ceil((bucket.expires_at - now).total_seconds()))
            bucket.attempts += 1
            bucket.save(update_fields=["attempts", "expires_at"])
    return None


@sensitive_post_parameters("password")
@csrf_protect
@require_http_methods(["GET", "POST", "DELETE"])
def session(request):
    if request.method == "GET":
        return JsonResponse(session_data(request))
    if request.method == "DELETE":
        logger.info("Logout", extra={"event": "logout"})
        logout(request)
        return HttpResponse(status=204)
    body = request.read(4097)
    if len(body) > 4096:
        return api_error("request_too_large", "Żądanie jest za duże.", 413)
    if request.content_type != "application/json":
        return api_error("validation_error", "Wymagany JSON.", 400)
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return api_error("validation_error", "Niepoprawne dane.", 400)
    if (
        not isinstance(data, dict)
        or set(data) != {"username", "password"}
        or not isinstance(data.get("username"), str)
        or not 1 <= len(data["username"]) <= 150
        or not isinstance(data.get("password"), str)
        or not 1 <= len(data["password"]) <= 1024
    ):
        return api_error("validation_error", "Niepoprawne dane.", 400)
    try:
        get_user_model()._meta.get_field("username").run_validators(data["username"])
    except ValidationError:
        return api_error("validation_error", "Niepoprawne dane.", 400)
    retry = reserve_attempt(data["username"], request.META.get("REMOTE_ADDR", "unknown"))
    if retry:
        logger.warning("Login limited", extra={"event": "login_limited"})
        response = api_error("rate_limited", "Zbyt wiele prób. Spróbuj później.", 429)
        response["Retry-After"] = str(retry)
        return response
    user = authenticate(request, username=data["username"], password=data["password"])
    if user is None:
        logger.info("Login failed", extra={"event": "login_failed"})
        return api_error("invalid_credentials", "Niepoprawne dane logowania.", 403)
    logger.info("Login succeeded", extra={"event": "login_success"})
    login(request, user)
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    return JsonResponse(session_data(request))
