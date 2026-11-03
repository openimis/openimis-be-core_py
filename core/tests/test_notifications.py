from django.test import TestCase
from graphene import Schema
from graphene.test import Client

from core.models import Notification, Role
from core.notifications import notify
from core.schema import Mutation, Query
from core.test_helpers import create_test_interactive_user, create_test_role
from core.models.openimis_graphql_test_case import BaseTestContext


class NotificationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="notification_user")
        cls.other = create_test_interactive_user(username="notification_other")
        cls.role = create_test_role(name="Notification role")
        cls.user.i_user.user_roles.create(role=Role.objects.get(id=cls.role.id))

    def context(self, user):
        return BaseTestContext(user).get_request()

    def execute(self, query, user, variables=None):
        client = Client(Schema(query=Query, mutation=Mutation))
        return client.execute(query, variables=variables, context=self.context(user))

    def test_notify_role_creates_one_retry_safe_row_per_user(self):
        for _ in range(2):
            notify(
                self.role,
                "task.assigned",
                "notification.task.title",
                "notification.task.message",
                idempotency_key="task:1:assigned",
            )
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 1)

    def test_inbox_is_private_and_mark_read_is_idempotent(self):
        notify(
            self.user,
            "task.assigned",
            "notification.task.title",
            "notification.task.message",
        )[0]
        query = "{ unreadNotificationCount notifications(first: 10) { edges { node { id uuid type readAt } } } }"
        own = self.execute(query, self.user)
        other = self.execute(query, self.other)
        self.assertEqual(own["data"]["unreadNotificationCount"], 1)
        self.assertEqual(len(own["data"]["notifications"]["edges"]), 1)
        self.assertEqual(other["data"]["unreadNotificationCount"], 0)

        mutation = "mutation($ids: [UUID]!) { markNotificationsRead(ids: $ids) { updatedCount } }"
        variables = {"ids": [own["data"]["notifications"]["edges"][0]["node"]["uuid"]]}
        first = self.execute(mutation, self.user, variables)
        second = self.execute(mutation, self.user, variables)
        self.assertEqual(first["data"]["markNotificationsRead"]["updatedCount"], 1)
        self.assertEqual(second["data"]["markNotificationsRead"]["updatedCount"], 0)
