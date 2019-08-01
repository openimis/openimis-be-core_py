from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from .models import Control, ModuleConfiguration, TechnicalUser
from .forms import TechnicalUserForm, TechnicalUserAdmin, GroupAdmin

admin.site.unregister(Group)

admin.site.register(Control)
admin.site.register(ModuleConfiguration)
admin.site.register(TechnicalUser, TechnicalUserAdmin)
admin.site.register(Permission)
admin.site.register(Group, GroupAdmin)
