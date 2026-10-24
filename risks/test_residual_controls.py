from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase
from django.urls import reverse

from core.test_helpers import TenantTestCase
from organizations.models import Membership
from .assessment import classify_score
from .models import Risk, RiskControl


class ResidualRiskTests(TenantTestCase):
    def test_gross_properties_unchanged_and_residual_independent(self):
        self.risk.likelihood, self.risk.impact = 5, 5
        self.risk.residual_likelihood, self.risk.residual_impact = 1, 4
        self.risk.save()
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.risk_score, 25)
        self.assertEqual(self.risk.risk_class.code, 'critical')
        self.assertEqual(self.risk.residual_risk_score, 4)
        self.assertEqual(self.risk.residual_risk_class.code, 'low')

    def test_all_residual_scores_and_classes(self):
        for likelihood in range(1, 6):
            for impact in range(1, 6):
                self.risk.residual_likelihood = likelihood
                self.risk.residual_impact = impact
                self.assertEqual(self.risk.residual_risk_score, likelihood * impact)
                self.assertEqual(self.risk.residual_risk_class, classify_score(likelihood * impact))

    def test_shared_classification_boundaries(self):
        # 17 is a policy boundary, but not a product of two integers from 1 to 5.
        for score, code in ((1, 'low'), (4, 'low'), (5, 'medium'), (9, 'medium'),
                            (10, 'high'), (16, 'high'), (17, 'critical'), (25, 'critical')):
            self.assertEqual(classify_score(score).code, code)

    def test_residual_validation_in_model_and_database(self):
        for field in ('residual_likelihood', 'residual_impact'):
            for value in (0, 6):
                setattr(self.risk, field, value)
                with self.assertRaises(ValidationError):
                    self.risk.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Risk.objects.filter(pk=self.risk.pk).update(**{field: value})
                setattr(self.risk, field, 3)

    def test_calculated_fields_cannot_be_assigned(self):
        for field in ('risk_score', 'risk_class', 'residual_risk_score', 'residual_risk_class'):
            with self.assertRaises(AttributeError):
                setattr(self.risk, field, 1)

    def test_post_manipulation_is_ignored_and_text_fields_saved(self):
        for url in ('/risks/new/', reverse('risks:edit', args=[self.risk.pk])):
            data = self.risk_payload(url, likelihood=5, impact=5, residual_likelihood=2,
                residual_impact=3, risk_source='Technischer Defekt', potential_impact='Ausfall',
                risk_score=1, risk_class='low', residual_risk_score=25, residual_risk_class='critical')
            self.assertEqual(self.client.post(url, data).status_code, 302)
            risk = Risk.objects.latest('pk') if url == '/risks/new/' else Risk.objects.get(pk=self.risk.pk)
            self.assertEqual(risk.risk_score, 25)
            self.assertEqual(risk.residual_risk_score, 6)
            self.assertEqual(risk.residual_risk_class.code, 'medium')
            self.assertEqual(risk.risk_source, 'Technischer Defekt')
            self.assertEqual(risk.potential_impact, 'Ausfall')

    def test_form_requires_valid_residual_values(self):
        for value in ('', 0, 6, '1.5', 'invalid'):
            response = self.client.post('/risks/new/', self.risk_payload('/risks/new/', residual_likelihood=value))
            self.assertIn('residual_likelihood', response.context['form'].errors)
        self.assertEqual(Risk.objects.count(), 2)

    def test_preview_shows_both_values_without_saving(self):
        url = reverse('risks:edit', args=[self.risk.pk])
        response = self.client.post(url, self.risk_payload(url, action='preview', likelihood=5, impact=5,
                                                         residual_likelihood=1, residual_impact=2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].assessment['score'], 25)
        self.assertEqual(response.context['form'].residual_assessment['score'], 2)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.risk_score, 9)
        self.assertEqual(self.risk.residual_risk_score, 9)

    def test_new_text_fields_are_escaped(self):
        self.risk.risk_source = '<script>source</script>'
        self.risk.potential_impact = '<script>impact</script>'
        self.risk.save()
        response = self.client.get(reverse('risks:detail', args=[self.risk.pk]))
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;source')
        self.assertContains(response, '&lt;script&gt;impact')

    def test_gross_and_residual_matrix_positions(self):
        self.risk.likelihood, self.risk.impact = 5, 5
        self.risk.residual_likelihood, self.risk.residual_impact = 1, 1
        self.risk.save()
        for kind, expected in (('gross', (5, 5)), ('residual', (1, 1)), ('invalid', (5, 5))):
            response = self.client.get('/risks/matrix/', {'type': kind})
            cells = {(c['likelihood'], c['impact']): c for r in response.context['matrix_rows'] for c in r['cells']}
            self.assertEqual(cells[expected]['risks'], [self.risk])
            self.assertEqual(sum(c['count'] for c in cells.values()), 1)
            self.assertNotContains(response, self.other_risk.title)
            self.assertContains(response, 'Restrisikomatrix' if kind == 'residual' else 'Bruttorisikomatrix')

    def test_residual_matrix_authorization(self):
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.get('/risks/matrix/?type=residual').status_code, 200)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get('/risks/matrix/?type=residual', follow=True).status_code, 403)
        self.client.logout()
        response = self.client.get('/risks/matrix/?type=residual')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/login/'))

    def test_residual_matrix_and_dashboard_switch_organization(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        self.select_organization(self.other_organization)
        response = self.client.get('/risks/matrix/?type=residual')
        self.assertContains(response, self.other_risk.title)
        self.assertNotContains(response, self.risk.title)
        self.assertEqual(self.client.get('/dashboard/').context['residual_risk_class_counts']['medium'], 1)

    def test_dashboard_counts_both_assessments_per_organization(self):
        self.risk.likelihood, self.risk.impact = 5, 5
        self.risk.residual_likelihood, self.risk.residual_impact = 1, 1
        self.risk.save()
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['risk_class_counts'], {'low': 0, 'medium': 0, 'high': 0, 'critical': 1})
        self.assertEqual(response.context['residual_risk_class_counts'], {'low': 1, 'medium': 0, 'high': 0, 'critical': 0})
        self.assertEqual(response.context['counts']['total'], 1)

    def test_residual_class_filter_combines_with_gross_filter(self):
        self.risk.likelihood, self.risk.impact = 5, 5
        self.risk.residual_likelihood, self.risk.residual_impact = 1, 1
        self.risk.save()
        response = self.client.get('/risks/', {'risk_class': 'critical', 'residual_risk_class': 'low'})
        self.assertEqual(list(response.context['risks']), [self.risk])
        response = self.client.get('/risks/', {'residual_risk_class': 'medium'})
        self.assertEqual(list(response.context['risks']), [])


class RiskControlTests(TenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.control = RiskControl.objects.create(risk=cls.risk, title='Vorhandene Kontrolle')
        cls.other_control = RiskControl.objects.create(risk=cls.other_risk, title='Fremde Kontrolle')

    def url(self, action, control=None, risk=None):
        risk, control = risk or self.risk, control or self.control
        args = [risk.pk] if action == 'create' else [risk.pk, control.pk]
        return reverse(f'risks:control-{action}', args=args)

    def payload(self, **overrides):
        data = {'title': 'Neue Kontrolle', 'description': 'Beschreibung', 'control_type': '',
                'effectiveness': 3, 'responsible_user': ''}
        data.update(overrides)
        return data

    def test_model_derives_organization_and_preserves_optional_fields(self):
        self.assertEqual(self.control.organization, self.organization)
        self.assertEqual(self.control.control_type, '')
        self.assertIsNone(self.control.responsible_user)
        self.assertIsNotNone(self.control.created_at)
        self.assertIsNotNone(self.control.updated_at)
        self.assertEqual(str(self.control), 'Vorhandene Kontrolle')

    def test_model_blocks_cross_organization_assignment(self):
        with self.assertRaises(ValidationError):
            RiskControl.objects.create(risk=self.risk, organization=self.other_organization, title='Invalid')
        self.control.risk = self.other_risk
        with self.assertRaises(ValidationError):
            self.control.save()

    def test_model_rejects_foreign_responsible_user(self):
        self.control.responsible_user = self.other_user
        with self.assertRaises(ValidationError):
            self.control.save()

    def test_risk_cannot_switch_organization_with_controls(self):
        self.risk.organization = self.other_organization
        with self.assertRaises(ValidationError):
            self.risk.save()

    def test_effectiveness_validation(self):
        for value in (0, 6):
            self.control.effectiveness = value
            with self.assertRaises(ValidationError):
                self.control.save()
            with self.assertRaises(IntegrityError), transaction.atomic():
                RiskControl.objects.filter(pk=self.control.pk).update(effectiveness=value)

    def test_control_changes_do_not_change_either_risk_assessment(self):
        original_updated_at = self.risk.updated_at
        for value in range(1, 6):
            self.control.effectiveness = value
            self.control.save()
            self.risk.refresh_from_db()
            self.assertEqual(self.risk.risk_score, 9)
            self.assertEqual(self.risk.residual_risk_score, 9)
            self.assertEqual(self.risk.updated_at, original_updated_at)

    def test_all_write_roles_create_and_edit(self):
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER,
                     Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            self.set_role(role)
            self.assertEqual(self.client.get(self.url('create')).status_code, 200)
            response = self.client.post(self.url('create'), self.payload(title=role, responsible_user=self.user.pk))
            self.assertRedirects(response, reverse('risks:detail', args=[self.risk.pk]))
            created = RiskControl.objects.get(title=role)
            self.assertEqual(created.organization, self.organization)
            self.assertEqual(created.responsible_user, self.user)
            self.assertEqual(self.client.get(self.url('edit', created)).status_code, 200)
            response = self.client.post(self.url('edit', created), self.payload(title=role, effectiveness=5,
                                       control_type=RiskControl.ControlType.PREVENTIVE))
            self.assertEqual(response.status_code, 302)
            created.refresh_from_db()
            self.assertEqual(created.effectiveness, 5)
            self.assertEqual(created.control_type, RiskControl.ControlType.PREVENTIVE)

    def test_viewer_can_view_but_cannot_create_or_edit(self):
        self.set_role(Membership.Role.VIEWER)
        self.assertContains(self.client.get(self.url('detail')), self.control.title)
        response = self.client.get(reverse('risks:detail', args=[self.risk.pk]))
        self.assertContains(response, self.control.title)
        self.assertNotContains(response, self.url('create'))
        self.assertNotContains(response, self.url('edit'))
        for action in ('create', 'edit'):
            self.assertEqual(self.client.get(self.url(action)).status_code, 403)
            self.assertEqual(self.client.post(self.url(action), self.payload()).status_code, 403)
        self.assertEqual(RiskControl.objects.count(), 2)
        self.control.refresh_from_db()
        self.assertEqual(self.control.title, 'Vorhandene Kontrolle')

    def test_foreign_risk_and_control_urls_are_blocked(self):
        for risk in (self.risk, self.other_risk):
            for action in ('detail', 'edit'):
                url = self.url(action, self.other_control, risk)
                self.assertEqual(self.client.get(url).status_code, 404)
                if action == 'edit':
                    self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        url = self.url('create', risk=self.other_risk)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('risks:detail', args=[self.risk.pk])), self.other_control.title)

    def test_second_membership_does_not_bypass_active_context(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.organization)
        self.test_foreign_risk_and_control_urls_are_blocked()

    def test_wrong_parent_within_same_organization_is_blocked(self):
        risk = Risk.objects.create(title='Anderes Risiko', organization=self.organization, created_by=self.user)
        self.assertEqual(self.client.get(self.url('detail', risk=risk)).status_code, 404)
        self.assertEqual(self.client.post(self.url('edit', risk=risk), self.payload()).status_code, 404)

    def test_post_cannot_reassign_risk_or_organization(self):
        for action in ('create', 'edit'):
            response = self.client.post(self.url(action), self.payload(risk=self.other_risk.pk,
                organization=self.other_organization.pk, id=self.other_control.pk))
            self.assertEqual(response.status_code, 302)
            control = RiskControl.objects.latest('pk') if action == 'create' else RiskControl.objects.get(pk=self.control.pk)
            self.assertEqual(control.risk, self.risk)
            self.assertEqual(control.organization, self.organization)
        self.other_control.refresh_from_db()
        self.assertEqual(self.other_control.title, 'Fremde Kontrolle')

    def test_foreign_inactive_or_disabled_responsible_user_rejected(self):
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

    def test_responsible_choices_only_show_own_active_members(self):
        response = self.client.get(self.url('create'))
        self.assertEqual(list(response.context['form'].fields['responsible_user'].queryset), [self.user])

    def test_revoked_membership_and_role_are_rechecked(self):
        self.client.get(self.url('create'))
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.post(self.url('create'), self.payload()).status_code, 403)
        self.membership.is_active = False
        self.membership.save()
        for action in ('create', 'detail', 'edit'):
            self.assertEqual(self.client.get(self.url(action), follow=True).status_code, 403)
        self.assertEqual(RiskControl.objects.count(), 2)

    def test_switched_organization_rejects_stale_control_form(self):
        self.client.get(self.url('create'))
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.other_organization)
        self.assertEqual(self.client.post(self.url('create'), self.payload()).status_code, 404)

    def test_anonymous_and_csrf_protection(self):
        self.client.logout()
        for action in ('create', 'detail', 'edit'):
            url = self.url(action)
            self.assertRedirects(self.client.get(url), f'/login/?next={url}', fetch_redirect_response=False)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for action in ('create', 'edit'):
            self.assertEqual(client.post(self.url(action), self.payload()).status_code, 403)

    def test_invalid_fields_and_escaped_content(self):
        for values in ({'title': ''}, {'control_type': 'INVALID'}, {'effectiveness': 6}):
            response = self.client.post(self.url('create'), self.payload(**values))
            self.assertTrue(response.context['form'].errors)
        self.control.description = '<script>alert(1)</script>'
        self.control.save()
        response = self.client.get(self.url('detail'))
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_admin_access_and_derived_organization(self):
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.client.get(reverse('admin:risks_riskcontrol_changelist')).status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(reverse('admin:risks_riskcontrol_add'), {
            **self.payload(), 'risk': self.risk.pk, 'organization': self.other_organization.pk, '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RiskControl.objects.latest('pk').organization, self.organization)
        self.assertEqual(self.client.get(reverse('admin:risks_riskcontrol_change', args=[self.control.pk])).status_code, 200)


class ResidualMigrationTests(TransactionTestCase):
    def test_existing_gross_values_are_copied_without_other_changes(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [('risks', '0002_riskmeasure_risk_impact_risk_likelihood_and_more')]
        try:
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            user = apps.get_model('accounts', 'User').objects.create(username='legacy-residual')
            organization = apps.get_model('organizations', 'Organization').objects.create(name='Bestand')
            old_risks = []
            for likelihood in range(1, 6):
                for impact in range(1, 6):
                    old_risks.append(apps.get_model('risks', 'Risk').objects.create(
                        title=f'Bestand {likelihood}/{impact}', description='Unveraendert', status='CLOSED',
                        likelihood=likelihood, impact=impact, treatment_strategy='REDUCE',
                        organization_id=organization.pk, created_by_id=user.pk,
                    ))
            measure = apps.get_model('risks', 'RiskMeasure').objects.create(
                risk_id=old_risks[0].pk, organization_id=organization.pk, title='Bestandsmassnahme',
            )
            MigrationExecutor(connection).migrate(latest)
            for old in old_risks:
                current = Risk.objects.get(pk=old.pk)
                self.assertEqual(current.residual_likelihood, old.likelihood)
                self.assertEqual(current.residual_impact, old.impact)
                self.assertEqual(current.residual_risk_score, current.risk_score)
                for field in ('title', 'description', 'likelihood', 'impact', 'status', 'treatment_strategy',
                              'organization_id', 'created_by_id', 'created_at', 'updated_at'):
                    self.assertEqual(getattr(current, field), getattr(old, field))
                self.assertEqual(current.risk_source, '')
                self.assertEqual(current.potential_impact, '')
            self.assertEqual(RiskControl.objects.count(), 0)
            self.assertEqual(Risk.objects.get(pk=old_risks[0].pk).measures.get().pk, measure.pk)
        finally:
            MigrationExecutor(connection).migrate(latest)
