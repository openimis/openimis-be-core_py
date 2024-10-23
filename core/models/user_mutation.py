import logging
import sys
import uuid
from datetime import datetime as py_datetime
from datetime import timedelta

from cached_property import cached_property
from django.apps import apps

# from core.datetimes.ad_datetime import datetime as py_datetime
from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    Group,
    PermissionsMixin,
)
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import models
from django.utils.crypto import salted_hmac
from graphql import ResolveInfo

import core

from ..utils import filter_validity
from .base import *
from .base_mutation import *
from .user import *
from .versioned_model import *

logger = logging.getLogger(__name__)


class RoleMutation(UUIDModel, ObjectMutation):
    role = models.ForeignKey(Role, models.DO_NOTHING, related_name="mutations")
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name="roles")

    class Meta:
        managed = True
        db_table = "core_RoleMutation"


class UserMutation(UUIDModel, ObjectMutation):
    core_user = models.ForeignKey(User, models.CASCADE, related_name="mutations")
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name="users")

    class Meta:
        managed = True
        db_table = "core_UserMutation"
