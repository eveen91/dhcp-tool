from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .access import ACTIONS, visible_firewalls
from .auth import api_error, role_for
from .draft_views import create_firewall, firewall_data


@require_http_methods(["GET", "POST"])
def firewalls(request):
    if request.method == "POST":
        return create_firewall(request)
    if role_for(request.user) not in ACTIONS["read"]:
        return api_error("authentication_required", "Wymagane konto z nadaną rolą.", 403)
    if set(request.GET) - {"page", "page_size", "search", "archived", "ordering"}:
        return api_error("validation_error", "Nieobsługiwane parametry.", 400)
    try:
        page = int(request.GET.get("page", "1"))
        size = int(request.GET.get("page_size", "50"))
        if not 1 <= page <= 2147483647 or not 1 <= size <= 100:
            raise ValueError
    except ValueError:
        return api_error("validation_error", "Niepoprawna paginacja.", 400)
    queryset = visible_firewalls(request.user)
    archived = request.GET.get("archived")
    if archived is not None:
        if archived not in ("true", "false"):
            return api_error("validation_error", "Niepoprawny filtr.", 400)
        queryset = queryset.filter(archived=archived == "true")
    if "search" in request.GET:
        queryset = queryset.filter(name__icontains=request.GET["search"][:150])
    ordering = request.GET.get("ordering", "name")
    if ordering not in ("name", "-name", "created_at", "-created_at"):
        return api_error("validation_error", "Niepoprawne sortowanie.", 400)
    queryset = queryset.order_by(ordering, "id")
    count = queryset.count()

    def link(number):
        params = request.GET.copy()
        params["page"] = str(number)
        return request.path + "?" + params.urlencode()

    return JsonResponse(
        {
            "count": count,
            "next": link(page + 1) if page * size < count else None,
            "previous": link(page - 1) if page > 1 else None,
            "results": [firewall_data(fw) for fw in queryset[(page - 1) * size : page * size]],
        }
    )
