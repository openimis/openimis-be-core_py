from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import password_validation, get_user_model
from django.contrib.auth.models import Group
from .models import TechnicalUser

User = get_user_model()

class TechnicalUserForm(forms.ModelForm):
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput,
        help_text=password_validation.password_validators_help_text_html(),
    )    
    class Meta:
        model = TechnicalUser
        fields = ['username', 'email', 'is_superuser', 'validity_from', 'validity_to']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.is_staff=self.cleaned_data["is_superuser"]
        if commit:
            user.save()
        return user        

class TechnicalUserAdmin(admin.ModelAdmin):
    form = TechnicalUserForm

class GroupAdminForm(forms.ModelForm):
    class Meta:
        model = Group
        exclude = []

    users = forms.ModelMultipleChoiceField(
         queryset=User.objects.all(), 
         required=False,
         widget=FilteredSelectMultiple('users', False)
    )

    def __init__(self, *args, **kwargs):
        super(GroupAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['users'].initial = self.instance.user_set.all()

    def save_m2m(self):
        self.instance.user_set.set(self.cleaned_data['users'])

    def save(self, *args, **kwargs):
        instance = super(GroupAdminForm, self).save(commit=True)
        self.save_m2m()
        return instance    

class GroupAdmin(admin.ModelAdmin):
    form = GroupAdminForm
    filter_horizontal = ['permissions']