from django.contrib.auth import get_user_model
from django.test import TestCase


class UserTests(TestCase):
    def test_create_user(self):
        user = get_user_model().objects.create_user('alice', password='test-password')
        self.assertEqual(user._meta.label, 'accounts.User')
        self.assertEqual(str(user), 'alice')
        self.assertTrue(user.check_password('test-password'))
        self.assertFalse(user.is_staff)

    def test_create_superuser(self):
        user = get_user_model().objects.create_superuser('admin', password='test-password')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
