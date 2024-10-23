from dataclasses import dataclass
from unittest.mock import PropertyMock, patch

from django.conf import settings
from django.db import connection
from graphql_jwt.shortcuts import get_token
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import User
from core.test_helpers import create_test_interactive_user


@dataclass
class DummyContext:
    """Just because we need a context to generate."""

    user: User


class ReportAPITests(APITestCase):

    admin_user = None
    admin_token = None
    UA_URL = (
        f"/{settings.SITE_ROOT()}"
        + "report/user_activity/pdf/?date_start=2019-10-01&date_end=2019-10-31"
    )
    RS_URL = f"/{settings.SITE_ROOT()}report/registers_status/pdf/"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(username="testLocationAdmin")
        cls.admin_token = get_token(cls.admin_user, DummyContext(user=cls.admin_user))

    def test_single_user_activity_report(self):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        response = self.client.get(
            self.UA_URL, **headers
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_single_registers_status_report(self):
        with patch(
            "core.models.InteractiveUser.is_imis_admin", new_callable=PropertyMock
        ) as mock_is_imis_admin:
            mock_is_imis_admin.return_value = False
            with self.settings(ROW_SECURITY=True):
                headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
                response = self.client.get(self.RS_URL, **headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

