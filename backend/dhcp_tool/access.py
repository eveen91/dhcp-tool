"""Fail-closed firewall scope, shared by every nested API operation."""

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404

from .auth import api_error, role_for
from .models import Firewall, Role

ACTIONS = {
    "read": {Role.READER, Role.EDITOR, Role.OPERATOR, Role.ADMIN},
    "edit": {Role.EDITOR, Role.ADMIN},
    "deploy": {Role.OPERATOR, Role.ADMIN},
    "admin": {Role.ADMIN},
}


def firewall_action(action):
    if action not in ACTIONS:
        raise ValueError("Unknown firewall action")

    def decorate(view):
        view.firewall_action = action
        return view

    return decorate


def firewall_child(parameter, model, *, firewall_lookup="firewall_id", source="path"):
    if source not in ("path", "query"):
        raise ValueError("Unknown identifier source")

    def decorate(view):
        children = dict(getattr(view, "firewall_children", {}))
        children[parameter] = (model, firewall_lookup, source)
        view.firewall_children = children
        return view

    return decorate


def visible_firewalls(user):
    role = role_for(user)
    if role not in ACTIONS["read"]:
        return Firewall.objects.none()
    if role == Role.ADMIN:
        return Firewall.objects.all()
    return Firewall.objects.filter(access_grants__user=user)


def scoped_object(queryset, firewall, identifier, *, firewall_lookup="firewall_id"):
    """Never resolve a child identifier before constraining its owning firewall."""
    return get_object_or_404(queryset.filter(**{firewall_lookup: firewall.pk}), pk=identifier)


class FirewallScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view, args, kwargs):
        if not request.path.startswith("/api/v1/firewalls/"):
            return None
        if "firewall_id" not in kwargs:
            if request.path == "/api/v1/firewalls/":
                return None
            return api_error("permission_denied", "Brak zakresu dostępu.", 403)
        if not request.user.is_authenticated:
            return api_error("authentication_required", "Wymagane logowanie.", 403)
        try:
            firewall = get_object_or_404(visible_firewalls(request.user), pk=kwargs["firewall_id"])
        except Http404:
            return api_error("not_found", "Nie znaleziono zasobu.", 404)
        # New mutation handlers must explicitly declare their capability.
        action = getattr(
            view, "firewall_action", "read" if request.method in ("GET", "HEAD") else None
        )
        if isinstance(action, dict):
            action = action.get(request.method)
            if action is None:
                return api_error("method_not_allowed", "Niedozwolona metoda.", 405)
        if action not in ACTIONS or role_for(request.user) not in ACTIONS[action]:
            return api_error("permission_denied", "Brak uprawnień do operacji.", 403)
        if firewall.archived and action in ("edit", "deploy"):
            return api_error("firewall_archived", "Firewall jest zarchiwizowany.", 409)
        declarations = getattr(view, "firewall_children", {})
        path_parameters = {key for key in kwargs if key.endswith("_id") and key != "firewall_id"}
        query_parameters = {
            key for key in request.GET if key.endswith("_id") or key in {"from", "to"}
        }
        if path_parameters & query_parameters:
            return api_error("validation_error", "Niejednoznaczny identyfikator.", 400)
        parameters = path_parameters | query_parameters
        if parameters - declarations.keys():
            return api_error("not_found", "Nie znaleziono zasobu.", 404)
        request.scoped_objects = {}
        for parameter in parameters:
            model, lookup, source = declarations[parameter]
            expected_source = "path" if parameter in path_parameters else "query"
            if source != expected_source:
                return api_error("not_found", "Nie znaleziono zasobu.", 404)
            if source == "query" and len(request.GET.getlist(parameter)) != 1:
                return api_error("validation_error", "Niejednoznaczny identyfikator.", 400)
            identifier = kwargs[parameter] if source == "path" else request.GET[parameter]
            try:
                request.scoped_objects[parameter] = scoped_object(
                    model.objects.all(), firewall, identifier, firewall_lookup=lookup
                )
            except (Http404, ValueError, TypeError, ValidationError):
                return api_error("not_found", "Nie znaleziono zasobu.", 404)
        request.firewall = firewall
        return None
