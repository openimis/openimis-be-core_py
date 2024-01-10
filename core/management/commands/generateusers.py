import random

from django.core.management.base import BaseCommand
from faker import Faker

from claim.test_helpers import create_test_claim_admin
from core.models import User
from core.test_helpers import create_test_interactive_user, create_test_technical_user, create_test_officer
from insuree.models import Insuree
from policyholder.tests import create_test_policy_holder_user, create_test_policy_holder_insuree
from policyholder.tests.helpers_tests import create_test_policy_holder


def _create_test_claim_admin(*args, **kwargs):
    username = kwargs.pop('username', None)
    claim_admin = create_test_claim_admin(**kwargs)
    return User.objects.create(username=username, claim_admin=claim_admin)


def _create_test_officer(*args, **kwargs):
    kwargs.pop('username', None)
    return create_test_officer(**kwargs)


class Command(BaseCommand):
    help = "This command will generate test Users with some optional parameters. It is intended to simulate larger" \
           "databases for performance testing"
    insurees = None
    users = None

    USER_TYPE_T = "t_user"
    USER_TYPE_I = "i_user"
    USER_TYPE_OFFICER = "officer"
    USER_TYPE_CLAIM_ADMIN = "claim_admin"
    RANDOM = "random"

    user_type_functions = {
        USER_TYPE_I: create_test_interactive_user,
        USER_TYPE_T: create_test_technical_user,
        USER_TYPE_OFFICER: _create_test_officer,
        USER_TYPE_CLAIM_ADMIN: _create_test_claim_admin,
    }

    def add_arguments(self, parser):
        parser.add_argument("nb_users", nargs=1, type=int)
        parser.add_argument("type", nargs=1, type=str, choices=[
            self.RANDOM, self.USER_TYPE_OFFICER, self.USER_TYPE_T, self.USER_TYPE_I, self.USER_TYPE_CLAIM_ADMIN
        ])
        parser.add_argument(
            '--verbose',
            action='store_true',
            dest='verbose',
            help='Be verbose about what it is doing',
        )
        parser.add_argument(
            '--locale',
            default="en",
            help="Used to adapt the fake names generation to the locale, using Faker, by default en",
        )

    def handle(self, *args, **options):
        fake = Faker(options["locale"])
        nb_users = options["nb_users"][0]
        user_type = options["type"][0]
        verbose = options["verbose"]
        for user_num in range(1, nb_users + 1):
            props = dict(
                username=fake.user_name(),
            )
            if user_type == self.RANDOM:
                random_type = random.choice(list(self.user_type_functions.keys()))
                user_type_create_function = self.user_type_functions[random_type]
            else:
                user_type_create_function = self.user_type_functions[user_type]

            user = user_type_create_function(**props)

            if verbose:
                print(user_num, "created user", user.username, user.pk)
