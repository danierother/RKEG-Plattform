from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test import Client
from django.urls import reverse

from organizations.models import Organization
from .models import Risk
from core.test_helpers import TenantTestCase
from organizations.models import Membership


class RiskTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('alice')
        self.organization = Organization.objects.create(name='Example')

    def test_defaults_relations_and_timestamps(self):
        risk = Risk.objects.create(
            organization=self.organization, title='Power outage', created_by=self.user,
        )
        risk.full_clean()
        self.assertEqual(str(risk), 'Power outage')
        self.assertEqual(risk.status, Risk.Status.OPEN)
        self.assertEqual(risk.description, '')
        self.assertEqual(self.organization.risks.get(), risk)
        self.assertEqual(self.user.created_risks.get(), risk)
        self.assertIsNotNone(risk.created_at)
        previous_updated_at = risk.updated_at
        risk.status = Risk.Status.IN_PROGRESS
        risk.save()
        risk.refresh_from_db()
        self.assertGreater(risk.updated_at, previous_updated_at)

    def test_organization_required_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Risk.objects.create(title='Power outage', created_by=self.user)

    def test_creator_required_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Risk.objects.create(title='Power outage', organization=self.organization)

    def test_status_validation(self):
        risk = Risk(organization=self.organization, title='Power outage', created_by=self.user)
        for status in Risk.Status:
            risk.status = status
            risk.full_clean()
        risk.status = 'UNKNOWN'
        with self.assertRaises(ValidationError):
            risk.full_clean()

    def test_organization_and_creator_deletion_protected(self):
        Risk.objects.create(organization=self.organization, title='Power outage', created_by=self.user)
        for obj in (self.organization, self.user):
            with self.assertRaises(ProtectedError):
                obj.delete()


class RiskViewTests(TenantTestCase):
    def test_list_is_organization_scoped(self):
        response = self.client.get('/risks/')
        self.assertContains(response, self.risk.title)
        self.assertNotContains(response, self.other_risk.title)
        self.assertEqual(list(response.context['risks']), [self.risk])

    def test_foreign_detail_and_edit_urls_blocked(self):
        for action in ('detail', 'edit'):
            url = reverse(f'risks:{action}', args=[self.other_risk.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            if action == 'edit':
                self.assertEqual(self.client.post(url, {'title': 'Manipuliert'}).status_code, 404)
        self.other_risk.refresh_from_db()
        self.assertEqual(self.other_risk.title, 'Vertrauliches Fremdrisiko')

    def test_nonexistent_risk_returns_404(self):
        for action in ('detail', 'edit'):
            self.assertEqual(self.client.get(reverse(f'risks:{action}', args=[999999])).status_code, 404)

    def test_other_active_membership_does_not_bypass_current_context(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.organization)
        self.test_foreign_detail_and_edit_urls_blocked()

    def test_all_write_roles_can_create(self):
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER,
                     Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            with self.subTest(role=role):
                self.set_role(role)
                data = self.risk_payload('/risks/new/', title=f'Risiko {role}')
                response = self.client.post('/risks/new/', data)
                risk = Risk.objects.get(title=data['title'])
                self.assertRedirects(response, reverse('risks:detail', args=[risk.pk]))
                self.assertEqual(risk.organization, self.organization)
                self.assertEqual(risk.created_by, self.user)

    def test_all_write_roles_can_edit(self):
        url = reverse('risks:edit', args=[self.risk.pk])
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER,
                     Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            with self.subTest(role=role):
                self.set_role(role)
                data = self.risk_payload(url, title=f'Bearbeitet {role}', status=Risk.Status.CLOSED)
                self.assertRedirects(self.client.post(url, data), reverse('risks:detail', args=[self.risk.pk]))
                self.risk.refresh_from_db()
                self.assertEqual(self.risk.title, data['title'])
                self.assertEqual(self.risk.status, Risk.Status.CLOSED)

    def test_viewer_can_read(self):
        self.set_role(Membership.Role.VIEWER)
        for url in ('/risks/', reverse('risks:detail', args=[self.risk.pk]), '/dashboard/'):
            response = self.client.get(url)
            self.assertContains(response, self.risk.title)
            self.assertNotContains(response, 'href="/risks/new/"')
            self.assertNotContains(response, f'href="/risks/{self.risk.pk}/edit/"')

    def test_viewer_cannot_create(self):
        self.set_role(Membership.Role.VIEWER)
        for method in ('get', 'post'):
            self.assertEqual(getattr(self.client, method)('/risks/new/').status_code, 403)
        self.assertEqual(Risk.objects.count(), 2)

    def test_viewer_cannot_edit(self):
        self.set_role(Membership.Role.VIEWER)
        url = reverse('risks:edit', args=[self.risk.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'title': 'Manipuliert'}).status_code, 403)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.title, 'Stromausfall')

    def test_create_ignores_forged_organization_and_creator(self):
        data = self.risk_payload('/risks/new/', organization=self.other_organization.pk,
                                 created_by=self.other_user.pk, id=self.other_risk.pk)
        self.assertEqual(self.client.post('/risks/new/', data).status_code, 302)
        risk = Risk.objects.get(title=data['title'])
        self.assertEqual(risk.organization, self.organization)
        self.assertEqual(risk.created_by, self.user)
        self.assertNotEqual(risk.pk, self.other_risk.pk)

    def test_edit_preserves_organization_and_original_creator(self):
        self.risk.created_by = self.other_user
        self.risk.save()
        url = reverse('risks:edit', args=[self.risk.pk])
        data = self.risk_payload(url, organization=self.other_organization.pk,
                                 created_by=self.user.pk, id=self.other_risk.pk)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.organization, self.organization)
        self.assertEqual(self.risk.created_by, self.other_user)
        self.other_risk.refresh_from_db()
        self.assertEqual(self.other_risk.title, 'Vertrauliches Fremdrisiko')

    def test_invalid_form_does_not_create_risk(self):
        for overrides in ({'title': ''}, {'status': 'UNKNOWN'}, {'title': 'a' * 256}):
            data = self.risk_payload('/risks/new/', **overrides)
            response = self.client.post('/risks/new/', data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(Risk.objects.count(), 2)

    def test_role_is_checked_again_on_post(self):
        data = self.risk_payload('/risks/new/')
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.post('/risks/new/', data).status_code, 403)

    def test_membership_is_checked_again_on_post(self):
        data = self.risk_payload('/risks/new/')
        self.membership.is_active = False
        self.membership.save()
        response = self.client.post('/risks/new/', data, follow=True)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Risk.objects.count(), 2)

    def test_roles_are_per_organization(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.VIEWER)
        self.select_organization(self.other_organization)
        self.assertEqual(self.client.get('/risks/new/').status_code, 403)
        self.assertEqual(self.client.get(reverse('risks:edit', args=[self.other_risk.pk])).status_code, 403)

    def test_stale_form_after_organization_switch_is_rejected(self):
        data = self.risk_payload('/risks/new/')
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.other_organization)
        response = self.client.post('/risks/new/', data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('organization_context', response.context['form'].errors)
        self.assertEqual(Risk.objects.count(), 2)

    def test_missing_or_forged_context_is_rejected(self):
        for token in ('', 'forged'):
            data = self.risk_payload('/risks/new/', organization_context=token)
            response = self.client.post('/risks/new/', data)
            self.assertIn('organization_context', response.context['form'].errors)
        self.assertEqual(Risk.objects.count(), 2)

    def test_pagination_is_scoped(self):
        Risk.objects.bulk_create([
            Risk(title=f'Risiko {index}', organization=self.organization, created_by=self.user)
            for index in range(26)
        ])
        for page, expected_length in ((1, 25), (2, 2)):
            response = self.client.get('/risks/', {'page': page})
            self.assertEqual(response.context['paginator'].count, 27)
            self.assertEqual(len(response.context['risks']), expected_length)
            self.assertNotContains(response, self.other_risk.title)

    def test_description_is_escaped(self):
        self.risk.description = '<script>alert(1)</script>'
        self.risk.save()
        response = self.client.get(reverse('risks:detail', args=[self.risk.pk]))
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in ('/risks/new/', reverse('risks:edit', args=[self.risk.pk]), '/organizations/select/'):
            self.assertEqual(client.post(url, {}).status_code, 403)
