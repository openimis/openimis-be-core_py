from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from .models import FieldControl, ModuleConfiguration, TechnicalUser
from .forms import TechnicalUserAdmin, GroupAdmin

admin.site.unregister(Group)

admin.site.register(FieldControl)
admin.site.register(ModuleConfiguration)
admin.site.register(TechnicalUser, TechnicalUserAdmin)
admin.site.register(Permission)
admin.site.register(Group, GroupAdmin)
