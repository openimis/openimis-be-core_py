from django.test import TestCase
from .security import ObjectPermissions, RemoteUserBackend
from .models import ModuleConfiguration


class ObjectPermissionsTest(TestCase):
    def test_perms_map(self):
        perms = ObjectPermissions()
        self.assertEquals(['core.view_moduleconfiguration'],
                          perms.get_required_object_permissions('GET', ModuleConfiguration))
        self.assertEquals(['core.add_moduleconfiguration'],
                          perms.get_required_object_permissions('POST', ModuleConfiguration))
        self.assertEquals(['core.change_moduleconfiguration'],
                          perms.get_required_object_permissions('PUT', ModuleConfiguration))
        self.assertEquals(['core.change_moduleconfiguration'],
                          perms.get_required_object_permissions('PATCH', ModuleConfiguration))
        self.assertEquals(['core.delete_moduleconfiguration'],
                          perms.get_required_object_permissions('DELETE', ModuleConfiguration))


class RemoteUserBackeTest(TestCase):
    def test_no_create_user(self):
        self.assertFalse(RemoteUserBackend().create_unknown_user)
