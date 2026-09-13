from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse

from core.test_helpers import TenantTestCase
from organizations.models import Membership
from .assessment import RiskBand, calculate_score, classify_score
from .models import Risk


class AssessmentPolicyTests(SimpleTestCase):
    def test_all_25_combinations(self):
        for likelihood in range(1, 6):
            for impact in range(1, 6):
                with self.subTest(likelihood=likelihood, impact=impact):
                    self.assertEqual(calculate_score(likelihood, impact), likelihood * impact)

    def test_class_boundaries(self):
        for score, code in ((1, 'low'), (4, 'low'), (5, 'medium'), (9, 'medium'),
                            (10, 'high'), (16, 'high'), (17, 'critical'), (25, 'critical')):
            self.assertEqual(classify_score(score).code, code)

    def test_invalid_values(self):
        for value in (0, 6, -1, 1.5, True, None, '3'):
            with self.assertRaises(ValueError):
                calculate_score(value, 3)
        for value in (0, 26, 9.5, True, None):
            with self.assertRaises(ValueError):
                classify_score(value)

    def test_alternative_thresholds(self):
        bands = (RiskBand('custom', 'Eigene Klasse', 1, 25),)
        self.assertEqual(classify_score(17, bands).code, 'custom')


class AssessmentModelAndViewTests(TenantTestCase):
    def test_defaults_and_computed_properties(self):
        self.assertEqual(self.risk.likelihood, 3)
        self.assertEqual(self.risk.impact, 3)
        self.assertEqual(self.risk.risk_score, 9)
        self.assertEqual(self.risk.risk_class.label, 'Mittel')
        self.risk.likelihood = 5
        self.risk.impact = 4
        self.assertEqual(self.risk.risk_score, 20)
        self.assertEqual(self.risk.risk_class.code, 'critical')
        with self.assertRaises(AttributeError):
            self.risk.risk_score = 1

    def test_scale_validated_by_model_and_database(self):
        for field in ('likelihood', 'impact'):
            for value in (0, 6):
                with self.subTest(field=field, value=value):
                    setattr(self.risk, field, value)
                    with self.assertRaises(ValidationError):
                        self.risk.full_clean()
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        Risk.objects.filter(pk=self.risk.pk).update(**{field: value})
                    setattr(self.risk, field, 3)

    def test_create_and_edit_ignore_forged_score_and_class(self):
        for url in ('/risks/new/', reverse('risks:edit', args=[self.risk.pk])):
            data = self.risk_payload(url, likelihood=5, impact=5, risk_score=1,
                                     risk_class='low', treatment_strategy=Risk.TreatmentStrategy.REDUCE)
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 302)
            risk = Risk.objects.get(pk=self.risk.pk) if '/edit/' in url else Risk.objects.latest('pk')
            self.assertEqual(risk.risk_score, 25)
            self.assertEqual(risk.risk_class.code, 'critical')
            self.assertEqual(risk.treatment_strategy, Risk.TreatmentStrategy.REDUCE)

    def test_form_rejects_invalid_scale_and_treatment(self):
        for overrides in ({'likelihood': 0}, {'impact': 6}, {'likelihood': '1.5'},
                          {'treatment_strategy': 'INVALID'}):
            response = self.client.post('/risks/new/', self.risk_payload('/risks/new/', **overrides))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(Risk.objects.count(), 2)

    def test_preview_does_not_create_or_update(self):
        for url in ('/risks/new/', reverse('risks:edit', args=[self.risk.pk])):
            response = self.client.post(url, self.risk_payload(url, likelihood=5, impact=4, action='preview'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['form'].assessment['score'], 20)
            self.assertContains(response, 'Kritisch')
        self.assertEqual(Risk.objects.count(), 2)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.risk_score, 9)

    def test_detail_and_register_show_assessment(self):
        for url in ('/risks/', reverse('risks:detail', args=[self.risk.pk])):
            response = self.client.get(url)
            self.assertContains(response, 'Risikowert')
            self.assertContains(response, 'risk-class-medium')

    def test_dashboard_class_counts_are_tenant_scoped(self):
        self.risk.likelihood, self.risk.impact = 1, 4
        self.risk.save()
        for likelihood, impact in ((1, 5), (3, 3), (2, 5), (4, 4), (4, 5), (5, 5)):
            Risk.objects.create(title='Bewertet', organization=self.organization,
                                created_by=self.user, likelihood=likelihood, impact=impact)
        Membership.objects.create(user=self.user, organization=self.other_organization)
        self.select_organization(self.organization)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['risk_class_counts'],
                         {'low': 1, 'medium': 2, 'high': 2, 'critical': 2})
        self.assertEqual(response.context['counts']['total'], 7)
        self.select_organization(self.other_organization)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['risk_class_counts'],
                         {'low': 0, 'medium': 1, 'high': 0, 'critical': 0})


class AssessmentMigrationTests(TransactionTestCase):
    def test_existing_risk_preserved(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([('risks', '0001_initial')])
            apps = executor.loader.project_state([('risks', '0001_initial')]).apps
            user = apps.get_model('accounts', 'User').objects.create(username='legacy')
            organization = apps.get_model('organizations', 'Organization').objects.create(name='Bestand')
            old = apps.get_model('risks', 'Risk').objects.create(
                organization_id=organization.pk, created_by_id=user.pk,
                title='Bestandsrisiko', description='Bestehende Daten', status='CLOSED',
            )
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            current = Risk.objects.get(pk=old.pk)
            self.assertEqual(current.risk_score, 9)
            self.assertEqual(current.treatment_strategy, '')
            for field in ('title', 'description', 'status', 'organization_id',
                          'created_by_id', 'created_at', 'updated_at'):
                self.assertEqual(getattr(current, field), getattr(old, field))
            self.assertEqual(current.measures.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
