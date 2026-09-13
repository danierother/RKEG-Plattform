from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Membership, Organization


class OrganizationTests(TestCase):
    def test_organization_optional_legal_name_and_timestamps(self):
        organization = Organization.objects.create(name='Example')
        organization.full_clean()
        self.assertEqual(str(organization), 'Example')
        self.assertEqual(organization.legal_name, '')
        self.assertIsNotNone(organization.pk)
        self.assertIsNotNone(organization.created_at)
        previous_updated_at = organization.updated_at
        organization.name = 'Updated'
        organization.save()
        organization.refresh_from_db()
        self.assertGreater(organization.updated_at, previous_updated_at)


class MembershipTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('alice')
        self.organization = Organization.objects.create(name='Example')

    def test_defaults_and_string(self):
        membership = Membership.objects.create(user=self.user, organization=self.organization)
        self.assertEqual(membership.role, Membership.Role.VIEWER)
        self.assertTrue(membership.is_active)
        self.assertIsNotNone(membership.created_at)
        self.assertEqual(str(membership), 'alice - Example (Viewer)')

    def test_multiple_organizations(self):
        other = Organization.objects.create(name='Other')
        for organization in (self.organization, other):
            Membership.objects.create(user=self.user, organization=organization)
        self.assertEqual(self.user.memberships.count(), 2)

    def test_duplicate_membership_rejected_by_database(self):
        Membership.objects.create(user=self.user, organization=self.organization)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(user=self.user, organization=self.organization)

    def test_roles(self):
        self.assertEqual(set(Membership.Role.values), {
            'ADMIN', 'RESILIENCE_MANAGER', 'RISK_MANAGER', 'EDITOR', 'VIEWER',
        })
        membership = Membership(user=self.user, organization=self.organization)
        for role in Membership.Role:
            membership.role = role
            membership.full_clean()
        membership.role = 'UNKNOWN'
        with self.assertRaises(ValidationError):
            membership.full_clean()
