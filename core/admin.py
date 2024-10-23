from django.contrib import admin
from django.contrib.auth.models import Group, Permission

from .forms import GroupAdmin, TechnicalUserAdmin
from .models import FieldControl, ModuleConfiguration, TechnicalUser

admin.site.unregister(Group)

admin.site.register(FieldControl)
admin.site.register(ModuleConfiguration)
admin.site.register(TechnicalUser, TechnicalUserAdmin)
admin.site.register(Permission)
admin.site.register(Group, GroupAdmin)
