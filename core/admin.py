from django.contrib import admin
from django.contrib.auth.models import Group, Permission
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
    list_display = ['user', 'content_type', 'object_id', 'date_valid_from', 'date_valid_to', 'active']
    list_filter = ['content_type', 'active']
    search_fields = ['user__username', 'object_id']
    raw_id_fields = ['user', 'content_type']
