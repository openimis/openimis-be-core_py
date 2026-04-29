import logging
from django.db import models

from .base import UUIDModel
from .user import User, Role
from .base_mutation import ObjectMutation, MutationLog

logger = logging.getLogger(__name__)


class RoleMutation(UUIDModel, ObjectMutation):
    role = models.ForeignKey(Role, models.DO_NOTHING, related_name="mutations")
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name="roles")

    class Meta:
        managed = True
        app_label = 'core'
        db_table = "core_RoleMutation"


class UserMutation(UUIDModel, ObjectMutation):
    core_user = models.ForeignKey(User, models.CASCADE, related_name="mutations")
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name="users")

    class Meta:
        managed = True
        db_table = "core_UserMutation"
