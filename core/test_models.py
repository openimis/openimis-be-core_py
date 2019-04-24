from django.test import TestCase
from .models import User, TechnicalUser, InteractiveUser


class UserTestCase(TestCase):

    def test_t_user_active_status(self):
        always_valid = User(username='always_valid',
                            t_user=TechnicalUser(username='always_valid'))
        self.assertTrue(always_valid.is_active)

        from core import datetime, datetimedelta
        not_yet_active = User(username='not_yet_active',
                              t_user=TechnicalUser(username='not_yet_active',
                                                   validity_from=datetime.datetime.now()+datetimedelta(days=1)))
        self.assertFalse(not_yet_active.is_active)

        not_active_anymore = User(username='not_active_anymore',
                                  t_user=TechnicalUser(username='not_active_anymore',
                                                       validity_to=datetime.datetime.now()+datetimedelta(days=-1)))
        self.assertFalse(not_active_anymore.is_active)

    def test_i_active_status(self):
        always_valid = User(username='always_valid',
                            i_user=InteractiveUser(login_name='always_valid'))
        self.assertTrue(always_valid.is_active)

        from core import datetime, datetimedelta
        not_yet_active = User(username='always_valid',
                              i_user=InteractiveUser(login_name='not_yet_active',
                                                     validity_from=datetime.datetime.now()+datetimedelta(days=1)))
        self.assertFalse(not_yet_active.is_active)

        not_active_anymore = User(username='always_valid',
                                  i_user=InteractiveUser(login_name='not_active_anymore',
                                                         validity_to=datetime.datetime.now()+datetimedelta(days=-1)))
        self.assertFalse(not_active_anymore.is_active)
