from django.contrib import admin, messages
from django.contrib.auth.models import Group, Permission
from .models import FieldControl, ModuleConfiguration, TechnicalUser
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from core.cache_control import (
    UnknownCacheAliasError,
    flush_caches,
    list_cache_info,
    resolve_cache_aliases,
)
from .models import FieldControl, ModuleConfiguration, TechnicalUser, UserBusinessAccess
from .forms import TechnicalUserAdmin, GroupAdmin

admin.site.unregister(Group)

admin.site.register(FieldControl)
admin.site.register(ModuleConfiguration)
admin.site.register(TechnicalUser, TechnicalUserAdmin)
admin.site.register(Permission)
admin.site.register(Group, GroupAdmin)


@admin.register(UserBusinessAccess)
class UserBusinessAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'link_type', 'content_type', 'object_id', 'date_valid_from', 'date_valid_to', 'active']
    list_filter = ['link_type', 'content_type', 'active']
    search_fields = ['user__username', 'object_id']
    raw_id_fields = ['user', 'content_type']


def cache_flush_view(request):
    """Admin page to flush all configured caches or selected aliases."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "flush_all":
            aliases = None
        else:
            aliases = request.POST.getlist("aliases")
            if not aliases:
                messages.error(request, _("Select at least one cache to flush."))
                return HttpResponseRedirect(request.path)
        try:
            resolved = resolve_cache_aliases(aliases)
        except UnknownCacheAliasError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(request.path)

        flushed, errors = flush_caches(resolved)
        if flushed:
            messages.success(
                request,
                _("Flushed cache(s): %(aliases)s")
                % {"aliases": ", ".join(flushed)},
            )
        for alias, message in errors:
            messages.error(
                request,
                _("Failed to flush cache '%(alias)s': %(message)s")
                % {"alias": alias, "message": message},
            )
        return HttpResponseRedirect(request.path)

    context = {
        **admin.site.each_context(request),
        "title": _("Caches"),
        "caches": list_cache_info(),
        "opts": {
            "app_label": "core",
            "app_config": {"verbose_name": "Core"},
        },
    }
    return TemplateResponse(request, "admin/core/cache_flush.html", context)


def _register_cache_flush_admin():
    if getattr(admin.site, "_core_cache_flush_registered", False):
        return
    admin.site._core_cache_flush_registered = True

    original_get_urls = admin.site.get_urls
    original_get_app_list = admin.site.get_app_list

    def get_urls():
        custom = [
            path(
                "core/cache/",
                admin.site.admin_view(cache_flush_view),
                name="core_cache_flush",
            ),
        ]
        return custom + original_get_urls()

    def get_app_list(request, app_label=None):
        app_list = original_get_app_list(request, app_label=app_label)
        if not getattr(request.user, "is_staff", False):
            return app_list
        if app_label is not None and app_label != "core":
            return app_list

        cache_model = {
            "name": str(_("Caches")),
            "object_name": "Cache",
            "perms": {
                "add": False,
                "change": True,
                "delete": False,
                "view": True,
            },
            "admin_url": reverse("admin:core_cache_flush"),
            "add_url": None,
            "view_only": False,
        }
        for app in app_list:
            if app.get("app_label") == "core":
                if not any(m.get("object_name") == "Cache" for m in app.get("models", [])):
                    app.setdefault("models", []).append(cache_model)
                return app_list
        app_list.append(
            {
                "name": "Core",
                "app_label": "core",
                "app_url": reverse("admin:app_list", args=("core",)),
                "has_module_perms": True,
                "models": [cache_model],
            }
        )
        return app_list

    admin.site.get_urls = get_urls
    admin.site.get_app_list = get_app_list


_register_cache_flush_admin()
