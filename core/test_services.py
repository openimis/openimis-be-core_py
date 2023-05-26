import importlib
import logging

from django.db import connection
from django.test.client import RequestFactory
from django.apps import apps

import core
from core.models import InteractiveUser, Officer, UserRole
from core.services import (
    create_or_update_interactive_user,
    create_or_update_core_user,
    create_or_update_officer,
    create_or_update_claim_admin,
    reset_user_password,
    set_user_password,
)
from django.test import TestCase
from location.models import OfficerVillage

logger = logging.getLogger(__file__)
postgresql = "postgresql"

class UserServicesTest(TestCase):
    claim_admin_class = None

    def setUp(self):
        super(UserServicesTest, self).setUp()
        # This shouldn't be necessary but cleanup from date tests tend not to cleanup properly
        core.calendar = importlib.import_module(".calendars.ad_calendar", "core")
        core.datetime = importlib.import_module(".datetimes.ad_datetime", "core")
        self.claim_admin_class = apps.get_model("claim", "ClaimAdmin")
        self.factory = RequestFactory()

    def test_iuser_min(self):
        roles = [11]
        username = "tstsvciu1"
        i_user, created = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name CIU1",
                other_names="Other 1 2 3",
                roles=roles,
                language="en",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEquals(i_user.username, username)
        self.assertEquals(i_user.last_name, "Last Name CIU1")
        self.assertEquals(i_user.other_names, "Other 1 2 3")
        self.assertEquals(i_user.role_id, roles[0])
        self.assertEquals(i_user.user_roles.count(), 1)
        self.assertEquals(i_user.user_roles.first().role_id, 11)
        self.assertEquals(i_user.language.code, "en")

        UserRole.objects.filter(user_id=i_user.id).delete()
        deleted_users = InteractiveUser.objects.filter(login_name=username).delete()
        logger.info(f"Deleted {deleted_users} users after test")

    def test_iuser_max(self):
        roles = [11, 12]
        username = "tstsvciu2"
        i_user, created = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name CIU2",
                other_names="Other 1 2 3",
                roles=roles,
                language="fr",
                phone="+123456789",
                email=f"{username}@illuminati.int",
                health_facility_id=1,
                password="foobar123",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEquals(i_user.username, username)
        self.assertEquals(i_user.last_name, "Last Name CIU2")
        self.assertEquals(i_user.other_names, "Other 1 2 3")
        self.assertTrue(i_user.role_id in roles)
        self.assertEquals(i_user.user_roles.count(), 2)
        self.assertEquals(
            list(i_user.user_roles.values_list("role_id", flat=True)), roles
        )
        self.assertEquals(i_user.language.code, "fr")
        self.assertEquals(i_user.phone, "+123456789")
        self.assertEquals(i_user.email, f"{username}@illuminati.int")
        self.assertIsNotNone(i_user.password)
        self.assertNotEqual(i_user.password, "foobar123")  # No clear text password
        self.assertTrue(i_user.check_password("foobar123"))
        self.assertFalse(i_user.check_password("wrong_password"))

        UserRole.objects.filter(user_id=i_user.id).delete()
        deleted_users = InteractiveUser.objects.filter(login_name=username).delete()
        logger.info(f"Deleted {deleted_users} users after test")

    def test_iuser_update(self):
        roles = [11, 12]
        roles2 = [8, 11]
        username = "tstsvciu2"
        i_user, created = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name CIU2",
                other_names="Other 1 2 3",
                roles=roles,
                language="fr",
                phone="+123456789",
                email=f"{username}@illuminati.int",
                health_facility_id=1,
                password="foobar123",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEquals(i_user.username, username)
        self.assertEquals(i_user.last_name, "Last Name CIU2")
        self.assertEquals(i_user.other_names, "Other 1 2 3")
        self.assertTrue(i_user.role_id in roles)
        self.assertEquals(i_user.user_roles.count(), 2)
        self.assertEquals(
            list(i_user.user_roles.values_list("role_id", flat=True)), roles
        )
        self.assertEquals(i_user.language.code, "fr")
        self.assertEquals(i_user.phone, "+123456789")
        self.assertEquals(i_user.email, f"{username}@illuminati.int")
        self.assertTrue(i_user.check_password("foobar123"))

        # Core user necessary for the update
        core_user, core_user_created = create_or_update_core_user(
            None, username, i_user=i_user
        )

        i_user2, created2 = create_or_update_interactive_user(
            user_id=core_user.id,
            data=dict(
                username=username,
                last_name="Last updated",
                other_names="Other updated",
                roles=roles2,
                language="en",
                phone="updated phone",
                email=f"{username}@updated.int",
                health_facility_id=2,
                password="updated",
            ),
            audit_user_id=111,
            connected=False,
        )
        self.assertFalse(created2)
        self.assertIsNotNone(i_user2)
        self.assertEquals(i_user2.username, username)
        self.assertEquals(i_user2.last_name, "Last updated")
        self.assertEquals(i_user2.other_names, "Other updated")
        self.assertTrue(i_user2.role_id in roles2)
        self.assertEquals(
            i_user2.user_roles.filter(validity_to__isnull=True).count(), 2
        )
        self.assertEquals(
            list(
                i_user2.user_roles.filter(validity_to__isnull=True)
                .order_by("role_id")
                .values_list("role_id", flat=True)
            ),
            roles2,
        )
        self.assertEquals(i_user2.language.code, "en")
        self.assertEquals(i_user2.phone, "updated phone")
        self.assertEquals(i_user2.email, f"{username}@updated.int")
        self.assertTrue(i_user2.check_password("updated"))

        UserRole.objects.filter(user_id=i_user.id).delete()
        core_user.delete()
        deleted_users = InteractiveUser.objects.filter(login_name=username).delete()
        logger.info(f"Deleted {deleted_users} users after test")

    def test_iuser_update_no_id(self):
        """
        This tests the update of a user without specifying a userId but with a username
        """
        roles = [11, 12]
        username = "tstsvciu3"
        i_user, created = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name CIU2",
                other_names="Other 1 2 3",
                roles=roles,
                language="fr",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEquals(i_user.username, username)

        i_user2, created2 = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last updated",
                other_names="Other updated",
                language="en",
                roles=roles,
            ),
            audit_user_id=111,
            connected=False,
        )
        self.assertFalse(created2)
        self.assertIsNotNone(i_user2)
        self.assertEquals(i_user2.username, username)
        self.assertEquals(i_user2.last_name, "Last updated")
        self.assertEquals(i_user2.other_names, "Other updated")

        UserRole.objects.filter(user_id=i_user.id).delete()
        deleted_users = InteractiveUser.objects.filter(login_name=username).delete()
        logger.info(f"Deleted {deleted_users} users after test")

    def test_officer_min(self):
        username = "tstsvco1"
        officer, created = create_or_update_officer(
            user_id=None,
            data=dict(
                username=username, last_name="Last Name O1", other_names="Other 1 2 3", phone="+12345678"
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(officer)
        self.assertEquals(officer.username, username)
        self.assertEquals(officer.last_name, "Last Name O1")
        self.assertEquals(officer.other_names, "Other 1 2 3")
        self.assertEquals(officer.phone, "+12345678")

        deleted_officers = Officer.objects.filter(code=username).delete()
        logger.info(f"Deleted {deleted_officers} officers after test")

    def test_officer_max(self):
        username = "tstsvco2"
        officer, created = create_or_update_officer(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name O2",
                other_names="Other 1 2 3",
                dob="1999-05-05",
                phone="+12345678",
                email="imis@foo.be",
                location_id=1,
                village_ids=[22, 35, 50],
                substitution_officer_id=1,
                works_to="2025-01-01",
                phone_communication=True,
                address="Multi\nline\naddress",
            ),
            audit_user_id=999,
            connected=True,
        )
        self.assertTrue(created)
        self.assertIsNotNone(officer)
        self.assertEquals(officer.username, username)
        self.assertEquals(officer.last_name, "Last Name O2")
        self.assertEquals(officer.other_names, "Other 1 2 3")
        self.assertEquals(officer.audit_user_id, 999)
        self.assertTrue(officer.has_login)
        self.assertTrue(officer.phone_communication)
        self.assertEquals(officer.location_id, 1)
        self.assertEquals(officer.substitution_officer_id, 1)
        self.assertEquals(officer.address, "Multi\nline\naddress")
        self.assertEquals(officer.works_to, "2025-01-01")
        self.assertEquals(
            list(
                OfficerVillage.objects.filter(validity_to__isnull=True, officer=officer)
                .order_by("location_id")
                .values_list("location_id", flat=True)
            ),
            [22, 35, 50],
        )
        self.assertEquals(officer.phone, "+12345678")
        self.assertEquals(officer.email, "imis@foo.be")

        deleted_officers = Officer.objects.filter(code=username).delete()
        logger.info(f"Deleted {deleted_officers} officers after test")

    def test_officer_update(self):
        username = "tstsvco2"
        officer, created = create_or_update_officer(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name O2",
                other_names="Other 1 2 3",
                dob="1999-05-05",
                phone="+12345678",
                email="imis@foo.be",
                location_id=1,
                village_ids=[22, 35, 50],
                substitution_officer_id=1,
                works_to="2025-01-01",
                phone_communication=True,
                address="Multi\nline\naddress",
            ),
            audit_user_id=999,
            connected=True,
        )
        self.assertTrue(created)
        self.assertIsNotNone(officer)
        self.assertEquals(officer.username, username)
        self.assertEquals(officer.last_name, "Last Name O2")
        self.assertEquals(officer.other_names, "Other 1 2 3")
        self.assertEquals(officer.audit_user_id, 999)
        self.assertTrue(officer.has_login)
        self.assertTrue(officer.phone_communication)
        self.assertEquals(officer.location_id, 1)
        self.assertEquals(officer.substitution_officer_id, 1)
        self.assertEquals(officer.address, "Multi\nline\naddress")
        self.assertEquals(officer.works_to, "2025-01-01")
        self.assertEquals(
            list(
                OfficerVillage.objects.filter(validity_to__isnull=True, officer=officer)
                .order_by("location_id")
                .values_list("location_id", flat=True)
            ),
            [22, 35, 50],
        )
        self.assertEquals(officer.phone, "+12345678")
        self.assertEquals(officer.email, "imis@foo.be")

        officer2, created = create_or_update_officer(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last updated",
                other_names="Other updated",
                dob="1999-01-01",
                phone="+00000",
                email="imis@bar.be",
                location_id=17,
                village_ids=[22],
                substitution_officer_id=None,
                works_to="2025-05-05",
                phone_communication=False,
                address="updated address",
            ),
            audit_user_id=111,
            connected=True,
        )
        self.assertFalse(created)
        self.assertIsNotNone(officer2)
        self.assertEquals(officer2.username, username)
        self.assertEquals(officer2.last_name, "Last updated")
        self.assertEquals(officer2.other_names, "Other updated")
        self.assertEquals(officer2.audit_user_id, 111)
        self.assertTrue(officer2.has_login)
        self.assertFalse(officer2.phone_communication)
        self.assertEquals(officer2.location_id, 17)
        self.assertIsNone(officer2.substitution_officer_id)
        self.assertEquals(officer2.address, "updated address")
        self.assertEquals(officer2.works_to, "2025-05-05")
        self.assertEquals(
            list(
                OfficerVillage.objects.filter(
                    validity_to__isnull=True, officer=officer2
                )
                .order_by("location_id")
                .values_list("location_id", flat=True)
            ),
            [22],
        )
        self.assertEquals(officer2.phone, "+00000")
        self.assertEquals(officer2.email, "imis@bar.be")

        deleted_officers = Officer.objects.filter(code=username).delete()
        logger.info(f"Deleted {deleted_officers} officers after test")

    def test_claim_admin_min(self):
        username = "tstsvca1"
        claim_admin, created = create_or_update_claim_admin(
            user_id=None,
            data=dict(
                username=username, last_name="Last Name CA1", other_names="Other 1 2 3"
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(claim_admin)
        self.assertEquals(claim_admin.username, username)
        self.assertEquals(claim_admin.last_name, "Last Name CA1")
        self.assertEquals(claim_admin.other_names, "Other 1 2 3")

        deleted_officers = Officer.objects.filter(code=username).delete()
        logger.info(f"Deleted {deleted_officers} officers after test")

    def test_claim_admin_max(self):
        username = "tstsvca2"
        claim_admin, created = create_or_update_claim_admin(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name CA2",
                other_names="Other 1 2 3",
                dob="1999-05-05",
                phone="+12345678",
                email="imis@foo.be",
                health_facility_id=1,
            ),
            audit_user_id=999,
            connected=True,
        )
        self.assertTrue(created)
        self.assertIsNotNone(claim_admin)
        self.assertEquals(claim_admin.username, username)
        self.assertEquals(claim_admin.last_name, "Last Name CA2")
        self.assertEquals(claim_admin.other_names, "Other 1 2 3")
        self.assertEquals(claim_admin.audit_user_id, 999)
        self.assertTrue(claim_admin.has_login)
        self.assertEquals(claim_admin.health_facility_id, 1)
        self.assertEquals(claim_admin.phone, "+12345678")
        self.assertEquals(claim_admin.email_id, "imis@foo.be")

        deleted_officers = Officer.objects.filter(code=username).delete()
        logger.info(f"Deleted {deleted_officers} officers after test")

    def test_user_reset_password(self):
        from django.core import mail

        roles = [11, 12]
        username = "user_reset"
        i_user, created = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="LN",
                other_names="ON",
                roles=roles,
                language="fr",
                phone="+123456789",
                email=f"{username}@illuminati.int",
                health_facility_id=1,
                password="foobar123",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertTrue(i_user.check_password("foobar123"))

        # Core user necessary for the update
        core_user, core_user_created = create_or_update_core_user(
            None, username, i_user=i_user
        )
        request = self.factory.get("/")

        reset_user_password(request, username)

        self.assertTrue(len(mail.outbox) == 1)
        self.assertTrue(mail.outbox[0].subject == "[OpenIMIS] Reset Password")

        UserRole.objects.filter(user_id=i_user.id).delete()
        if connection.vendor == postgresql:
            UserRole.objects.filter(user_id=core_user.id).delete()
        core_user.delete()
        i_user.delete()

    def test_user_set_password(self):
        roles = [11, 12]
        username = "user_set"
        i_user, created = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="LN",
                other_names="ON",
                roles=roles,
                language="fr",
                phone="+123456789",
                email=f"{username}@illuminati.int",
                health_facility_id=1,
                password="foobar123",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertTrue(i_user.check_password("foobar123"))
        # Core user necessary for the update
        core_user, _ = create_or_update_core_user(None, username, i_user=i_user)

        from django.core.exceptions import ValidationError

        request = self.factory.get("/")
        with self.assertRaises(ValidationError):
            set_user_password(request, username, "TOKEN", "new_password")

        UserRole.objects.filter(user_id=i_user.id).delete()
        if connection.vendor == postgresql:
            UserRole.objects.filter(user_id=core_user.id).delete()
        core_user.delete()
        i_user.delete()
