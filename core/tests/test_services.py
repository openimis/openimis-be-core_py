import importlib
import logging
import datetime

from django.test.client import RequestFactory
from django.apps import apps
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed, ParseError

import core
from core.models import InteractiveUser, Language, User
from core.services import (
    create_or_update_interactive_user,
    create_or_update_core_user,
    create_or_update_officer,
    create_or_update_claim_admin,
    reset_user_password,
    set_user_password,
    user_authentication,
)
from core.test_helpers import (
    create_test_interactive_user,
    create_test_role,
)
from location.models import OfficerVillage
from location.test_helpers import create_test_village, create_test_health_facility
logger = logging.getLogger(__file__)
PASSWORD = "FoBoar72!"


class UserServicesTest(TestCase):
    claim_admin_class = None

    def setUp(self):
        super(UserServicesTest, self).setUp()
        # This shouldn't be necessary but cleanup from date tests tend not to cleanup properly
        core.calendar = importlib.import_module(".calendars.ad_calendar", "core")
        core.datetime = importlib.import_module(".datetimes.ad_datetime", "core")
        self.claim_admin_class = apps.get_model("core", "ClaimAdmin")
        self.factory = RequestFactory()
        # Create test villages
        self.test_village1 = create_test_village(custom_props={"name": "Test Village 1", "code": "TV1"})
        self.test_village2 = create_test_village(custom_props={"name": "Test Village 2", "code": "TV2"})
        self.test_village3 = create_test_village(custom_props={"name": "Test Village 3", "code": "TV3"})

        # Create French language if it doesn't exist
        Language.objects.get_or_create(
            code="fr",
            defaults={"name": "Français", "sort_order": 1}
        )

        # Create test health facility
        self.test_hf = create_test_health_facility()
        self.test_hf2 = create_test_health_facility()
        self.user = create_test_interactive_user()

    def test_create_iuser_required_fields_only(self):
        role_id = create_test_role().id
        roles = [role_id]
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
            user_maker=self.user,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEqual(i_user.username, username)
        self.assertEqual(i_user.last_name, "Last Name CIU1")
        self.assertEqual(i_user.other_names, "Other 1 2 3")
        self.assertEqual(i_user.user_roles.count(), 1)
        self.assertEqual(i_user.user_roles.first().role_id, role_id)
        self.assertEqual(i_user.language.code, "en")

    def test_create_iuser_with_optional_fields(self):
        roles = [create_test_role(name="TestRole1").id, create_test_role(name="TestRole2").id]
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
                health_facility_id=self.test_hf.id,
                password=PASSWORD,
            ),
            user_maker=self.user,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEqual(i_user.username, username)
        self.assertEqual(i_user.last_name, "Last Name CIU2")
        self.assertEqual(i_user.other_names, "Other 1 2 3")
        self.assertEqual(i_user.user_roles.count(), 2)
        self.assertEqual(
            list(i_user.user_roles.values_list("role_id", flat=True)), roles
        )
        self.assertEqual(i_user.language.code, "fr")
        self.assertEqual(i_user.phone, "+123456789")
        self.assertEqual(i_user.email, f"{username}@illuminati.int")
        self.assertIsNotNone(i_user.password)
        self.assertNotEqual(i_user.password, PASSWORD)  # No clear text password
        self.assertTrue(i_user.check_password(PASSWORD))
        self.assertFalse(i_user.check_password("wrong_password"))

    def test_iuser_update(self):
        roles = [create_test_role(name="TestRole1").id, create_test_role(name="TestRole2").id]
        roles2 = [create_test_role(name="TestRole3").id, create_test_role(name="TestRole4").id]
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
                health_facility_id=self.test_hf.id,
                password=PASSWORD,
            ),
            user_maker=self.user,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEqual(i_user.username, username)
        self.assertEqual(i_user.last_name, "Last Name CIU2")
        self.assertEqual(i_user.other_names, "Other 1 2 3")
        self.assertEqual(i_user.user_roles.count(), 2)
        self.assertEqual(
            list(i_user.user_roles.values_list("role_id", flat=True)), roles
        )
        self.assertEqual(i_user.language.code, "fr")
        self.assertEqual(i_user.phone, "+123456789")
        self.assertEqual(i_user.email, f"{username}@illuminati.int")
        self.assertTrue(i_user.check_password(PASSWORD))

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
                health_facility_id=self.test_hf2.id,
                password=f"{PASSWORD}updated",
            ),
            user_maker=self.user,
            connected=False,
        )
        self.assertFalse(created2)
        self.assertIsNotNone(i_user2)
        self.assertEqual(i_user2.username, username)
        self.assertEqual(i_user2.last_name, "Last updated")
        self.assertEqual(i_user2.other_names, "Other updated")
        self.assertEqual(
            i_user2.user_roles.filter(validity_to__isnull=True).count(), 2
        )
        self.assertEqual(
            list(
                i_user2.user_roles.filter(validity_to__isnull=True)
                .order_by("role_id")
                .values_list("role_id", flat=True)
            ),
            roles2,
        )
        self.assertEqual(i_user2.language.code, "en")
        self.assertEqual(i_user2.phone, "updated phone")
        self.assertEqual(i_user2.email, f"{username}@updated.int")
        self.assertTrue(i_user2.check_password(f"{PASSWORD}updated"))

    def test_iuser_update_no_id(self):
        """
        This tests the update of a user without specifying a userId but with a username
        """
        roles = [create_test_role(name="TestRole1").id, create_test_role(name="TestRole2").id]
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
            user_maker=self.user,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(i_user)
        self.assertEqual(i_user.username, username)

        i_user2, created2 = create_or_update_interactive_user(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last updated",
                other_names="Other updated",
                language="en",
                roles=roles,
            ),
            user_maker=self.user,
            connected=False,
        )
        self.assertFalse(created2)
        self.assertIsNotNone(i_user2)
        self.assertEqual(i_user2.username, username)
        self.assertEqual(i_user2.last_name, "Last updated")
        self.assertEqual(i_user2.other_names, "Other updated")

    def test_officer_min(self):
        username = "tstsvco1"
        officer, created = create_or_update_officer(
            user_id=None,
            data=dict(
                username=username,
                last_name="Last Name O1",
                other_names="Other 1 2 3",
                phone="+12345678",
            ),
            audit_user_id=999,
            connected=False,
        )
        self.assertTrue(created)
        self.assertIsNotNone(officer)
        self.assertEqual(officer.username, username)
        self.assertEqual(officer.last_name, "Last Name O1")
        self.assertEqual(officer.other_names, "Other 1 2 3")
        self.assertEqual(officer.phone, "+12345678")

    def test_officer_max(self):
        username = "tstsvco2"
        village_ids = [self.test_village1.id, self.test_village2.id, self.test_village3.id]
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
                village_ids=village_ids,
                substitution_officer_id=1,
                works_to="2025-01-01",
                phone_communication=True,
                address="Multi\nline\naddress",
            ),
            audit_user_id=999,
            connected=True,
        )
        officer.refresh_from_db()
        self.assertTrue(created)
        self.assertIsNotNone(officer)
        self.assertEqual(officer.username, username)
        self.assertEqual(officer.last_name, "Last Name O2")
        self.assertEqual(officer.other_names, "Other 1 2 3")
        self.assertEqual(officer.audit_user_id, 999)
        self.assertTrue(officer.has_login)
        self.assertTrue(officer.phone_communication)
        self.assertEqual(officer.location_id, 1)
        self.assertEqual(officer.substitution_officer_id, 1)
        self.assertEqual(officer.address, "Multi\nline\naddress")
        self.assertEqual(str(officer.works_to.date()), "2025-01-01")
        self.assertEqual(
            list(
                OfficerVillage.objects.filter(validity_to__isnull=True, officer=officer)
                .order_by("location_id")
                .values_list("location_id", flat=True)
            ),
            sorted(village_ids),
        )
        self.assertEqual(officer.phone, "+12345678")
        self.assertEqual(officer.email, "imis@foo.be")

    def test_officer_update(self):
        username = "tstsvco2"
        village_ids = [self.test_village1.id, self.test_village2.id, self.test_village3.id]
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
                village_ids=village_ids,
                substitution_officer_id=1,
                works_to="2025-01-01",
                phone_communication=True,
                address="Multi\nline\naddress",
            ),
            audit_user_id=999,
            connected=True,
        )
        officer.refresh_from_db()
        self.assertTrue(created)
        self.assertIsNotNone(officer)
        self.assertEqual(officer.username, username)
        self.assertEqual(officer.last_name, "Last Name O2")
        self.assertEqual(officer.other_names, "Other 1 2 3")
        self.assertEqual(officer.audit_user_id, 999)
        self.assertTrue(officer.has_login)
        self.assertTrue(officer.phone_communication)
        self.assertEqual(officer.location_id, 1)
        self.assertEqual(officer.substitution_officer_id, 1)
        self.assertEqual(officer.address, "Multi\nline\naddress")
        self.assertEqual(str(officer.works_to.date()), "2025-01-01")
        self.assertEqual(
            list(
                OfficerVillage.objects.filter(validity_to__isnull=True, officer=officer)
                .order_by("location_id")
                .values_list("location_id", flat=True)
            ),
            sorted(village_ids),
        )
        self.assertEqual(officer.phone, "+12345678")
        self.assertEqual(officer.email, "imis@foo.be")

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
                village_ids=[self.test_village1.id],
                substitution_officer_id=None,
                works_to=datetime.date(2025, 5, 5),
                phone_communication=False,
                address="updated address",
            ),
            audit_user_id=111,
            connected=True,
        )
        self.assertFalse(created)
        self.assertIsNotNone(officer2)
        self.assertEqual(officer2.username, username)
        self.assertEqual(officer2.last_name, "Last updated")
        self.assertEqual(officer2.other_names, "Other updated")
        self.assertEqual(officer2.audit_user_id, 111)
        self.assertTrue(officer2.has_login)
        self.assertFalse(officer2.phone_communication)
        self.assertEqual(officer2.location_id, 17)
        self.assertIsNone(officer2.substitution_officer_id)
        self.assertEqual(officer2.address, "updated address")
        self.assertEqual(str(officer2.works_to.date()), "2025-05-05")
        self.assertEqual(
            list(
                OfficerVillage.objects.filter(
                    validity_to__isnull=True, officer=officer2
                )
                .order_by("location_id")
                .values_list("location_id", flat=True)
            ),
            [self.test_village1.id],
        )
        self.assertEqual(officer2.phone, "+00000")
        self.assertEqual(officer2.email, "imis@bar.be")

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
        self.assertEqual(claim_admin.username, username)
        self.assertEqual(claim_admin.last_name, "Last Name CA1")
        self.assertEqual(claim_admin.other_names, "Other 1 2 3")

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
                health_facility_id=self.test_hf.id,
            ),
            audit_user_id=999,
            connected=True,
        )
        self.assertTrue(created)
        self.assertIsNotNone(claim_admin)
        self.assertEqual(claim_admin.username, username)
        self.assertEqual(claim_admin.last_name, "Last Name CA2")
        self.assertEqual(claim_admin.other_names, "Other 1 2 3")
        self.assertEqual(claim_admin.audit_user_id, 999)
        self.assertTrue(claim_admin.has_login)
        self.assertEqual(claim_admin.health_facility_id, self.test_hf.id)
        self.assertEqual(claim_admin.phone, "+12345678")
        self.assertEqual(claim_admin.email_id, "imis@foo.be")

    def test_user_reset_password(self):
        from django.core import mail

        roles = [create_test_role(name="TestRole1").id, create_test_role(name="TestRole2").id]
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
                password=PASSWORD,
            ),
            user_maker=self.user,
            connected=False,
        )
        self.assertTrue(created)
        self.assertTrue(i_user.check_password(PASSWORD))

        # Core user necessary for the update
        core_user, core_user_created = create_or_update_core_user(
            None, username, i_user=i_user
        )
        request = self.factory.get("/")

        reset_user_password(request, username)

        self.assertTrue(len(mail.outbox) == 1)
        self.assertTrue(mail.outbox[0].subject == "[OpenIMIS] Reset Password")

    def test_user_set_password(self):
        roles = [create_test_role(name="TestRole1").id, create_test_role(name="TestRole2").id]
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
                password=PASSWORD,
            ),
            user_maker=self.user,
            connected=False,
        )
        self.assertTrue(created)
        self.assertTrue(i_user.check_password(PASSWORD))
        # Core user necessary for the update
        core_user, _ = create_or_update_core_user(None, username, i_user=i_user)

        from django.core.exceptions import ValidationError

        request = self.factory.get("/")
        with self.assertRaises(ValidationError):
            set_user_password(request, username, "TOKEN", "new_password")


class UserAuthenticationTest(TestCase):
    legacy_username = "legacy_user_test"
    legacy_password = "Legacy123!"

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        language, _ = Language.objects.get_or_create(
            code="en", defaults={"name": "English", "sort_order": 1}
        )
        self.legacy_i_user = InteractiveUser.objects.create(
            login_name=self.legacy_username,
            other_names="Legacy",
            last_name="User",
            language=language,
        )
        self.legacy_i_user.set_password(self.legacy_password)
        self.legacy_i_user.save()

    def test_missing_username_raises_parse_error(self):
        request = self.factory.post("/")
        with self.assertRaises(ParseError):
            user_authentication(request, None, "password")

        with self.assertRaises(ParseError):
            user_authentication(request, "", "password")

    def test_missing_password_raises_parse_error(self):
        request = self.factory.post("/")
        with self.assertRaises(ParseError):
            user_authentication(request, "username", None)

        with self.assertRaises(ParseError):
            user_authentication(request, "username", "")

    def test_auto_provision_creates_user_for_legacy_interactive_user(self):
        self.assertFalse(User.objects.filter(username=self.legacy_username).exists())

        request = self.factory.post("/")
        user = user_authentication(request, self.legacy_username, self.legacy_password)

        self.assertIsNotNone(user)
        self.assertTrue(User.objects.filter(username=self.legacy_username).exists())
        self.assertEqual(user.i_user.id, self.legacy_i_user.id)

    def test_auto_provision_fails_with_wrong_password(self):
        self.assertFalse(User.objects.filter(username=self.legacy_username).exists())

        request = self.factory.post("/")
        with self.assertRaises(AuthenticationFailed):
            user_authentication(request, self.legacy_username, "wrong_password")
