from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Membership, Organization
from core.test_helpers import TenantTestCase
from .mixins import ORGANIZATION_SESSION_KEY


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


class OrganizationContextTests(TenantTestCase):
    def test_single_membership_selected_automatically(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['active_organization'], self.organization)
        self.assertEqual(self.client.session[ORGANIZATION_SESSION_KEY], self.organization.pk)
        self.assertContains(response, 'Alex Muster')

    def test_multiple_memberships_require_selection(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        for url in ('/dashboard/', '/risks/', '/risks/new/', '/organizations/'):
            self.assertRedirects(self.client.get(url), '/organizations/select/')
        response = self.client.get('/organizations/select/')
        self.assertContains(response, self.organization.name)
        self.assertContains(response, self.other_organization.name)

    def test_valid_selection_changes_active_organization(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        response = self.client.post('/organizations/select/', {'organization': self.other_organization.pk})
        self.assertRedirects(response, '/dashboard/')
        self.assertEqual(self.client.session[ORGANIZATION_SESSION_KEY], self.other_organization.pk)
        self.assertContains(self.client.get('/risks/'), self.other_risk.title)
        self.assertNotContains(self.client.get('/risks/'), self.risk.title)

    def test_invalid_selection_does_not_change_context(self):
        self.select_organization(self.organization)
        for value in (self.other_organization.pk, 999999, 'invalid'):
            response = self.client.post('/organizations/select/', {'organization': value})
            self.assertEqual(response.status_code, 200)
            self.assertFormError(response.context['form'], 'organization',
                                 response.context['form'].errors['organization'])
            self.assertEqual(self.client.session[ORGANIZATION_SESSION_KEY], self.organization.pk)
            self.assertNotContains(response, self.other_organization.name)

    def test_inactive_membership_not_selectable(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, is_active=False)
        response = self.client.get('/organizations/select/')
        self.assertNotContains(response, self.other_organization.name)
        response = self.client.post('/organizations/select/', {'organization': self.other_organization.pk})
        self.assertTrue(response.context['form'].errors)

    def test_forged_session_does_not_grant_access(self):
        self.select_organization(self.other_organization)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['active_organization'], self.organization)
        self.assertNotContains(response, self.other_risk.title)

    def test_forged_session_with_multiple_memberships_requires_selection(self):
        third = Organization.objects.create(name='Dritte Organisation')
        Membership.objects.create(user=self.user, organization=third)
        self.select_organization(self.other_organization)
        self.assertRedirects(self.client.get('/dashboard/'), '/organizations/select/')
        self.assertNotIn(ORGANIZATION_SESSION_KEY, self.client.session)

    def test_revoked_membership_clears_selection(self):
        self.select_organization(self.organization)
        self.membership.is_active = False
        self.membership.save()
        response = self.client.get('/dashboard/', follow=True)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(ORGANIZATION_SESSION_KEY, self.client.session)
        self.assertNotContains(response, self.risk.title, status_code=403)

    def test_no_memberships_has_explanatory_page_without_redirect_loop(self):
        self.membership.delete()
        response = self.client.get('/dashboard/', follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, 'Keine aktive Mitgliedschaft', status_code=403)

    def test_superuser_needs_membership_in_application(self):
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()
        self.membership.delete()
        response = self.client.get('/risks/', follow=True)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, self.other_risk.title, status_code=403)

    def test_organization_page_only_shows_active_organization(self):
        response = self.client.get('/organizations/')
        self.assertContains(response, self.organization.name)
        self.assertNotContains(response, self.other_organization.name)
