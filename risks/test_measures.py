from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from core.test_helpers import TenantTestCase
from organizations.models import Membership
from .models import Risk, RiskMeasure


class RiskMeasureTests(TenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.measure = RiskMeasure.objects.create(risk=cls.risk, title='Notstrom pruefen')
        cls.foreign_measure = RiskMeasure.objects.create(risk=cls.other_risk, title='Fremde Massnahme')

    def url(self, action, measure=None, risk=None):
        measure = measure or self.measure
        risk = risk or self.risk
        args = [risk.pk] if action == 'create' else [risk.pk, measure.pk]
        return reverse(f'risks:measure-{action}', args=args)

    def payload(self, **overrides):
        values = {'title': 'Neue Massnahme', 'description': 'Beschreibung',
                  'status': RiskMeasure.Status.PLANNED, 'responsible_user': '', 'due_date': ''}
        values.update(overrides)
        return values

    def test_model_derives_organization_and_defaults(self):
        self.assertEqual(self.measure.organization, self.organization)
        self.assertEqual(self.measure.status, RiskMeasure.Status.PLANNED)
        self.assertIsNone(self.measure.responsible_user)
        self.assertIsNone(self.measure.due_date)
        self.assertEqual(str(self.measure), 'Notstrom pruefen')
        self.assertIsNotNone(self.measure.created_at)
        self.assertIsNotNone(self.measure.updated_at)

    def test_model_rejects_mismatched_organization(self):
        with self.assertRaises(ValidationError):
            RiskMeasure.objects.create(risk=self.risk, organization=self.other_organization, title='Invalid')

    def test_model_rejects_foreign_responsible_user(self):
        with self.assertRaises(ValidationError):
            RiskMeasure.objects.create(risk=self.risk, title='Invalid', responsible_user=self.other_user)

    def test_risk_with_measures_cannot_change_organization(self):
        self.risk.organization = self.other_organization
        with self.assertRaises(ValidationError):
            self.risk.save()

    def test_anonymous_redirects(self):
        self.client.logout()
        for action in ('create', 'detail', 'edit'):
            for method in ('get', 'post'):
                url = self.url(action)
                self.assertRedirects(getattr(self.client, method)(url), f'/login/?next={url}',
                                     fetch_redirect_response=False)

    def test_all_writing_roles_create_and_edit(self):
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER,
                     Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            with self.subTest(role=role):
                self.set_role(role)
                self.assertEqual(self.client.get(self.url('create')).status_code, 200)
                response = self.client.post(self.url('create'), self.payload(title=role,
                                            responsible_user=self.user.pk, due_date='2027-04-01'))
                self.assertRedirects(response, reverse('risks:detail', args=[self.risk.pk]))
                created = RiskMeasure.objects.get(title=role)
                self.assertEqual(created.organization, self.organization)
                self.assertEqual(created.responsible_user, self.user)
                self.assertEqual(str(created.due_date), '2027-04-01')
                for status in RiskMeasure.Status:
                    response = self.client.post(self.url('edit', measure=created),
                                                self.payload(title=role, status=status))
                    self.assertEqual(response.status_code, 302)
                    created.refresh_from_db()
                    self.assertEqual(created.status, status)

    def test_viewer_can_read_but_cannot_write(self):
        self.set_role(Membership.Role.VIEWER)
        self.assertContains(self.client.get(self.url('detail')), self.measure.title)
        response = self.client.get(reverse('risks:detail', args=[self.risk.pk]))
        self.assertContains(response, self.measure.title)
        self.assertNotContains(response, self.url('edit'))
        self.assertNotContains(response, self.url('create'))
        for action in ('create', 'edit'):
            self.assertEqual(self.client.get(self.url(action)).status_code, 403)
            self.assertEqual(self.client.post(self.url(action), self.payload()).status_code, 403)
        self.assertEqual(RiskMeasure.objects.count(), 2)
        self.measure.refresh_from_db()
        self.assertEqual(self.measure.title, 'Notstrom pruefen')

    def test_foreign_urls_and_mismatched_parent_blocked(self):
        for risk in (self.risk, self.other_risk):
            for action in ('detail', 'edit'):
                url = self.url(action, risk=risk, measure=self.foreign_measure)
                self.assertEqual(self.client.get(url).status_code, 404)
                if action == 'edit':
                    self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        url = self.url('create', risk=self.other_risk)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('risks:detail', args=[self.risk.pk])),
                               self.foreign_measure.title)

    def test_other_active_membership_does_not_bypass_scope(self):
        Membership.objects.create(user=self.user, organization=self.other_organization,
                                  role=Membership.Role.ADMIN)
        self.select_organization(self.organization)
        self.test_foreign_urls_and_mismatched_parent_blocked()

    def test_wrong_risk_in_same_organization_is_blocked(self):
        risk = Risk.objects.create(title='Weiteres Risiko', organization=self.organization, created_by=self.user)
        self.assertEqual(self.client.get(self.url('detail', risk=risk)).status_code, 404)
        self.assertEqual(self.client.post(self.url('edit', risk=risk), self.payload()).status_code, 404)

    def test_post_cannot_change_parent_or_organization(self):
        for action in ('create', 'edit'):
            data = self.payload(risk=self.other_risk.pk, organization=self.other_organization.pk,
                                id=self.foreign_measure.pk)
            self.assertEqual(self.client.post(self.url(action), data).status_code, 302)
            measure = RiskMeasure.objects.latest('pk') if action == 'create' else RiskMeasure.objects.get(pk=self.measure.pk)
            self.assertEqual(measure.risk, self.risk)
            self.assertEqual(measure.organization, self.organization)
        self.foreign_measure.refresh_from_db()
        self.assertEqual(self.foreign_measure.title, 'Fremde Massnahme')

    def test_foreign_and_inactive_responsible_user_rejected(self):
        for action in ('create', 'edit'):
            response = self.client.post(self.url(action), self.payload(responsible_user=self.other_user.pk))
            self.assertIn('responsible_user', response.context['form'].errors)
        membership = Membership.objects.create(user=self.other_user, organization=self.organization, is_active=False)
        response = self.client.post(self.url('create'), self.payload(responsible_user=self.other_user.pk))
        self.assertIn('responsible_user', response.context['form'].errors)
        membership.is_active = True
        membership.save()
        self.other_user.is_active = False
        self.other_user.save()
        response = self.client.post(self.url('create'), self.payload(responsible_user=self.other_user.pk))
        self.assertIn('responsible_user', response.context['form'].errors)

    def test_responsible_choices_are_scoped(self):
        response = self.client.get(self.url('create'))
        self.assertEqual(list(response.context['form'].fields['responsible_user'].queryset), [self.user])

    def test_revoked_writer_cannot_submit(self):
        self.client.get(self.url('create'))
        self.membership.is_active = False
        self.membership.save()
        for action in ('create', 'edit'):
            response = self.client.post(self.url(action), self.payload(), follow=True)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(RiskMeasure.objects.count(), 2)

    def test_organization_switch_rejects_stale_form_url(self):
        self.client.get(self.url('create'))
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.other_organization)
        self.assertEqual(self.client.post(self.url('create'), self.payload()).status_code, 404)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for action in ('create', 'edit'):
            self.assertEqual(client.post(self.url(action), self.payload()).status_code, 403)

    def test_invalid_fields_and_escaped_description(self):
        for changes in ({'title': ''}, {'status': 'INVALID'}, {'due_date': 'not-a-date'}):
            response = self.client.post(self.url('create'), self.payload(**changes))
            self.assertTrue(response.context['form'].errors)
        self.measure.description = '<script>alert(1)</script>'
        self.measure.save()
        response = self.client.get(self.url('detail'))
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_admin_remains_reserved_for_superusers(self):
        self.user.is_staff = True
        self.user.save()
        url = reverse('admin:risks_riskmeasure_changelist')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(reverse('admin:risks_riskmeasure_add'), {
            **self.payload(responsible_user=self.user.pk), 'risk': self.risk.pk,
            'organization': self.other_organization.pk, '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RiskMeasure.objects.latest('pk').organization, self.organization)

    def test_admin_risk_and_measure_change_forms_render(self):
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()
        for name, pk in (('risk', self.risk.pk), ('riskmeasure', self.measure.pk)):
            response = self.client.get(reverse(f'admin:risks_{name}_change', args=[pk]))
            self.assertEqual(response.status_code, 200)
