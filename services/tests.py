from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core.test_helpers import TenantTestCase
from incidents.models import Incident
from organizations.models import Membership
from risks.models import Risk
from .models import CriticalService, Location, ServiceDependency


class ServicesTestCase(TenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.location = Location.objects.create(organization=cls.organization, name='Wien Zentrale',
            city='Wien', description='Leitstelle', location_type=Location.LocationType.HEADQUARTERS)
        cls.foreign_location = Location.objects.create(organization=cls.other_organization, name='Fremder Standort')
        cls.service = CriticalService.objects.create(organization=cls.organization, name='Wasserversorgung',
            description='Trinkwasserbetrieb', criticality=4, recovery_priority=1)
        cls.foreign_service = CriticalService.objects.create(organization=cls.other_organization, name='Fremder Service',
            description='Vertraulich', criticality=5)
        cls.service.locations.add(cls.location)
        cls.dependency = ServiceDependency.objects.create(service=cls.service, name='Stromversorgung',
            dependency_type=ServiceDependency.DependencyType.ENERGY, criticality=4, single_point_of_failure=True)
        cls.foreign_dependency = ServiceDependency.objects.create(service=cls.foreign_service, name='Fremde Abhaengigkeit',
            criticality=5, single_point_of_failure=True)
        cls.when = timezone.now().replace(second=0, microsecond=0)
        cls.incident = Incident.objects.create(organization=cls.organization, created_by=cls.user, title='Eigener Vorfall',
            description='Text', impact_description='Text', occurred_at=cls.when, detected_at=cls.when,
            affected_service='Freitext Dienst', affected_location='Freitext Ort')
        cls.foreign_incident = Incident.objects.create(organization=cls.other_organization, created_by=cls.other_user,
            title='Fremder Vorfall', description='Text', impact_description='Text', occurred_at=cls.when, detected_at=cls.when)

    def url(self, name, obj=None, service=None):
        if name.startswith('dependency-'):
            args = [(service or self.service).pk]
            if name != 'dependency-create':
                args.append((obj or self.dependency).pk)
        elif name in ('list', 'create', 'location-list', 'location-create'):
            args = []
        else:
            args = [(obj or (self.location if name.startswith('location-') else self.service)).pk]
        return reverse(f'services:{name}', args=args)

    def payload(self, view_name='create', url=None, **overrides):
        response = self.client.get(url or self.url(view_name))
        self.assertEqual(response.status_code, 200)
        if view_name.startswith('location-'):
            data = {'name': 'Neuer Standort', 'location_type': 'OFFICE', 'is_active': 'on'}
        elif view_name.startswith('dependency-'):
            data = {'name': 'Neue Abhaengigkeit', 'dependency_type': 'IT', 'criticality': 3,
                    'internal_external': 'INTERNAL'}
        else:
            data = {'name': 'Neue Dienstleistung', 'description': 'Beschreibung', 'status': 'ACTIVE',
                    'criticality': 3, 'recovery_priority': 3, 'service_owner': '', 'locations': []}
        if 'organization_context' in response.context['form'].fields:
            data['organization_context'] = response.context['form']['organization_context'].value()
        data.update(overrides)
        return data

    def incident_payload(self, **overrides):
        response = self.client.get(reverse('incidents:edit', args=[self.incident.pk]))
        data = {'title': self.incident.title, 'description': 'Text', 'impact_description': 'Text',
            'occurred_at': timezone.localtime(self.when).strftime('%Y-%m-%dT%H:%M'),
            'detected_at': timezone.localtime(self.when).strftime('%Y-%m-%dT%H:%M'),
            'status': 'NEW', 'severity': 2, 'incident_type': 'OTHER', 'reporting_status': 'NOT_ASSESSED',
            'affected_service': 'Freitext Dienst', 'affected_location': 'Freitext Ort',
            'organization_context': response.context['form']['organization_context'].value()}
        data.update(overrides)
        return data


class ServiceModelTests(ServicesTestCase):
    def test_defaults_strings_and_derived_organization(self):
        self.assertEqual(str(self.location), self.location.name)
        self.assertEqual(str(self.service), self.service.name)
        self.assertEqual(str(self.dependency), self.dependency.name)
        self.assertEqual(self.dependency.organization, self.organization)
        self.assertTrue(self.location.is_active)
        self.assertIsNone(self.service.maximum_tolerable_downtime)
        self.assertIsNone(self.service.recovery_time_objective)

    def test_duration_validation_in_model_and_database(self):
        self.service.maximum_tolerable_downtime = timedelta(hours=2)
        self.service.recovery_time_objective = timedelta(hours=3)
        with self.assertRaises(ValidationError):
            self.service.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CriticalService.objects.filter(pk=self.service.pk).update(
                maximum_tolerable_downtime=timedelta(hours=2), recovery_time_objective=timedelta(hours=3))
        self.service.recovery_time_objective = timedelta(hours=2)
        self.service.save()
        self.service.refresh_from_db()
        self.assertEqual(self.service.recovery_time_objective, timedelta(hours=2))

    def test_zero_optional_and_negative_durations(self):
        for mtd, rto in ((None, None), (None, timedelta(hours=1)), (timedelta(0), None), (timedelta(0), timedelta(0))):
            self.service.maximum_tolerable_downtime, self.service.recovery_time_objective = mtd, rto
            self.service.save()
        self.assertEqual(self.service.rto_display, '00:00:00')
        for field in ('maximum_tolerable_downtime', 'recovery_time_objective'):
            self.service.refresh_from_db()
            setattr(self.service, field, timedelta(seconds=-1))
            with self.assertRaises(ValidationError):
                self.service.save()
            with self.assertRaises(IntegrityError), transaction.atomic():
                CriticalService.objects.filter(pk=self.service.pk).update(**{field: timedelta(seconds=-1)})

    def test_scale_database_constraints(self):
        for model, obj, field in ((CriticalService, self.service, 'criticality'),
                                  (CriticalService, self.service, 'recovery_priority'),
                                  (ServiceDependency, self.dependency, 'criticality')):
            for value in (0, 6):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.filter(pk=obj.pk).update(**{field: value})

    def test_organization_changes_and_mismatched_dependencies_blocked(self):
        for obj in (self.location, self.service, self.dependency):
            obj.organization = self.other_organization
            with self.assertRaises(ValidationError):
                obj.save()
            obj.refresh_from_db()
        with self.assertRaises(ValidationError):
            ServiceDependency.objects.create(service=self.service, organization=self.other_organization, name='Invalid')

    def test_foreign_service_owner_blocked_by_model(self):
        self.service.service_owner = self.other_user
        with self.assertRaises(ValidationError):
            self.service.save()

    def test_all_m2m_links_checked_in_both_directions(self):
        pairs = (
            (self.service.locations, self.foreign_location), (self.foreign_location.critical_services, self.service),
            (self.risk.critical_services, self.foreign_service), (self.foreign_service.risks, self.risk),
            (self.incident.affected_services, self.foreign_service), (self.foreign_service.incidents, self.incident),
            (self.incident.affected_locations, self.foreign_location), (self.foreign_location.incidents, self.incident),
        )
        for manager, foreign in pairs:
            with self.assertRaises(ValidationError), transaction.atomic():
                manager.add(foreign)

    def test_m2m_set_rolls_back_removals_on_invalid_add(self):
        with self.assertRaises(ValidationError), transaction.atomic():
            self.service.locations.set([self.foreign_location])
        self.assertEqual(list(self.service.locations.all()), [self.location])

    def test_linked_risk_cannot_change_organization(self):
        self.risk.critical_services.add(self.service)
        self.risk.organization = self.other_organization
        with self.assertRaises(ValidationError):
            self.risk.save()


class ServiceViewTests(ServicesTestCase):
    def test_location_create_assigns_organization(self):
        response = self.client.post(self.url('location-create'), self.payload('location-create',
            organization=self.other_organization.pk, id=self.foreign_location.pk))
        self.assertEqual(response.status_code, 302)
        location = Location.objects.get(name='Neuer Standort')
        self.assertEqual(location.organization, self.organization)

    def test_service_create_assigns_organization_and_locations(self):
        response = self.client.post(self.url('create'), self.payload(organization=self.other_organization.pk,
            locations=[self.location.pk], service_owner=self.user.pk, maximum_tolerable_downtime='1 00:00:00',
            recovery_time_objective='04:00:00'))
        service = CriticalService.objects.get(name='Neue Dienstleistung')
        self.assertRedirects(response, self.url('detail', service))
        self.assertEqual(service.organization, self.organization)
        self.assertEqual(service.service_owner, self.user)
        self.assertEqual(list(service.locations.all()), [self.location])
        self.assertEqual(service.maximum_tolerable_downtime, timedelta(days=1))
        self.assertEqual(service.recovery_time_objective, timedelta(hours=4))

    def test_foreign_location_and_service_not_visible_or_editable(self):
        for prefix, foreign in (('location-', self.foreign_location), ('', self.foreign_service)):
            response = self.client.get(self.url(prefix + 'list'))
            self.assertNotContains(response, foreign.name)
            for action in ('detail', 'edit'):
                url = self.url(prefix + action, foreign)
                self.assertEqual(self.client.get(url).status_code, 404)
                if action == 'edit':
                    self.assertEqual(self.client.post(url, {'name': 'Manipuliert'}).status_code, 404)

    def test_all_writing_roles_can_create_and_edit(self):
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER, Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            self.set_role(role)
            for name in ('create', 'edit', 'location-create', 'location-edit', 'dependency-create', 'dependency-edit'):
                response = self.client.post(self.url(name), self.payload(name, name=f'{name} {role}'))
                self.assertEqual(response.status_code, 302, (role, name))

    def test_viewer_can_only_read(self):
        self.set_role(Membership.Role.VIEWER)
        for name in ('list', 'detail', 'location-list', 'location-detail', 'dependency-detail'):
            response = self.client.get(self.url(name))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'href="' + self.url('edit') + '"')
        for name in ('create', 'edit', 'location-create', 'location-edit', 'dependency-create', 'dependency-edit'):
            self.assertEqual(self.client.get(self.url(name)).status_code, 403)
            self.assertEqual(self.client.post(self.url(name), {'name': 'Manipuliert'}).status_code, 403)

    def test_edit_does_not_move_organization(self):
        for name, obj in (('edit', self.service), ('location-edit', self.location), ('dependency-edit', self.dependency)):
            response = self.client.post(self.url(name), self.payload(name, organization=self.other_organization.pk))
            self.assertEqual(response.status_code, 302)
            obj.refresh_from_db()
            self.assertEqual(obj.organization, self.organization)

    def test_foreign_locations_rejected_on_create_and_edit(self):
        for name in ('create', 'edit'):
            response = self.client.post(self.url(name), self.payload(name, locations=[self.foreign_location.pk]))
            self.assertIn('locations', response.context['form'].errors)
            self.assertNotContains(response, self.foreign_location.name)
        self.assertEqual(list(self.service.locations.all()), [self.location])

    def test_foreign_inactive_disabled_owner_rejected(self):
        for name in ('create', 'edit'):
            response = self.client.post(self.url(name), self.payload(name, service_owner=self.other_user.pk))
            self.assertIn('service_owner', response.context['form'].errors)
        membership = Membership.objects.create(user=self.other_user, organization=self.organization, is_active=False)
        response = self.client.post(self.url('create'), self.payload(service_owner=self.other_user.pk))
        self.assertIn('service_owner', response.context['form'].errors)
        membership.is_active = True
        membership.save()
        self.other_user.is_active = False
        self.other_user.save()
        response = self.client.post(self.url('create'), self.payload(service_owner=self.other_user.pk))
        self.assertIn('service_owner', response.context['form'].errors)

    def test_rto_mtd_form_validation(self):
        for values in ({'maximum_tolerable_downtime': '01:00:00', 'recovery_time_objective': '02:00:00'},
                       {'recovery_time_objective': '-01:00:00'}, {'maximum_tolerable_downtime': 'invalid'}):
            response = self.client.post(self.url('create'), self.payload(**values))
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(CriticalService.objects.count(), 2)

    def test_dependency_derives_organization_and_preserves_booleans(self):
        data = self.payload('dependency-create', organization=self.other_organization.pk, service=self.foreign_service.pk,
                            single_point_of_failure='on', contingency_available='on')
        self.assertEqual(self.client.post(self.url('dependency-create'), data).status_code, 302)
        dependency = ServiceDependency.objects.latest('pk')
        self.assertEqual(dependency.service, self.service)
        self.assertEqual(dependency.organization, self.organization)
        self.assertTrue(dependency.single_point_of_failure)
        self.assertTrue(dependency.contingency_available)

    def test_foreign_dependency_and_parent_urls_blocked(self):
        self.assertEqual(self.client.get(self.url('dependency-create', service=self.foreign_service)).status_code, 404)
        self.assertEqual(self.client.post(self.url('dependency-create', service=self.foreign_service), {}).status_code, 404)
        for service in (self.service, self.foreign_service):
            for action in ('dependency-detail', 'dependency-edit'):
                url = self.url(action, self.foreign_dependency, service)
                self.assertEqual(self.client.get(url).status_code, 404)
                if action == 'dependency-edit':
                    self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_wrong_parent_in_same_organization_blocked(self):
        another = CriticalService.objects.create(organization=self.organization, name='Anderer Service', description='Text')
        self.assertEqual(self.client.get(self.url('dependency-detail', service=another)).status_code, 404)
        self.assertEqual(self.client.post(self.url('dependency-edit', service=another), {}).status_code, 404)

    def test_additional_membership_does_not_bypass_scope(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.organization)
        self.test_foreign_location_and_service_not_visible_or_editable()
        self.test_foreign_dependency_and_parent_urls_blocked()

    def test_revoked_membership_and_role_rechecked(self):
        data = self.payload()
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.post(self.url('create'), data).status_code, 403)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.post(self.url('create'), data, follow=True).status_code, 403)

    def test_stale_and_forged_context_rejected(self):
        data = self.payload()
        response = self.client.post(self.url('create'), {**data, 'organization_context': 'forged'})
        self.assertIn('organization_context', response.context['form'].errors)
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.other_organization)
        response = self.client.post(self.url('create'), data)
        self.assertIn('organization_context', response.context['form'].errors)
        self.assertEqual(self.client.post(self.url('dependency-create'), {}).status_code, 404)

    def test_anonymous_redirects_and_csrf(self):
        self.client.logout()
        for name in ('list', 'detail', 'create', 'edit', 'location-list', 'location-detail', 'location-create',
                     'location-edit', 'dependency-detail', 'dependency-create', 'dependency-edit'):
            url = self.url(name)
            for method in ('get', 'post'):
                self.assertRedirects(getattr(self.client, method)(url), f'/login/?next={url}', fetch_redirect_response=False)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name in ('create', 'edit', 'location-create', 'location-edit', 'dependency-create', 'dependency-edit'):
            self.assertEqual(client.post(self.url(name), {}).status_code, 403)

    def test_admin_superuser_read_only(self):
        self.user.is_staff = True
        self.user.save()
        for name in ('location', 'criticalservice', 'servicedependency'):
            self.assertEqual(self.client.get(reverse(f'admin:services_{name}_changelist')).status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        for name, obj in (('location', self.location), ('criticalservice', self.service), ('servicedependency', self.dependency)):
            self.assertEqual(self.client.get(reverse(f'admin:services_{name}_changelist')).status_code, 200)
            self.assertEqual(self.client.get(reverse(f'admin:services_{name}_change', args=[obj.pk])).status_code, 200)
            self.assertEqual(self.client.post(reverse(f'admin:services_{name}_add'), {}).status_code, 403)

    def test_content_escaped(self):
        self.service.description = '<script>alert(1)</script>'
        self.service.save()
        response = self.client.get(self.url('detail'))
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')


class ServiceIntegrationTests(ServicesTestCase):
    def test_risk_links_own_services(self):
        url = reverse('risks:edit', args=[self.risk.pk])
        self.assertEqual(self.client.post(url, self.risk_payload(url, critical_services=[self.service.pk])).status_code, 302)
        self.assertEqual(list(self.risk.critical_services.all()), [self.service])
        self.risk.refresh_from_db()
        self.assertContains(self.client.get(reverse('risks:detail', args=[self.risk.pk])), self.service.name)
        self.assertContains(self.client.get(self.url('detail')), self.risk.title)

    def test_risk_foreign_service_rejected_on_create_and_edit(self):
        for url in (reverse('risks:create'), reverse('risks:edit', args=[self.risk.pk])):
            response = self.client.post(url, self.risk_payload(url, critical_services=[self.foreign_service.pk]))
            self.assertIn('critical_services', response.context['form'].errors)
            self.assertNotContains(response, self.foreign_service.name)
        self.assertEqual(self.risk.critical_services.count(), 0)

    def test_incident_own_structured_links_preserve_freetext(self):
        url = reverse('incidents:edit', args=[self.incident.pk])
        response = self.client.post(url, self.incident_payload(affected_services=[self.service.pk], affected_locations=[self.location.pk]))
        self.assertEqual(response.status_code, 302)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.affected_service, 'Freitext Dienst')
        self.assertEqual(self.incident.affected_location, 'Freitext Ort')
        self.assertEqual(list(self.incident.affected_services.all()), [self.service])
        self.assertEqual(list(self.incident.affected_locations.all()), [self.location])
        self.assertContains(self.client.get(self.url('detail')), self.incident.title)

    def test_incident_foreign_links_rejected(self):
        for field, value in (('affected_services', self.foreign_service.pk), ('affected_locations', self.foreign_location.pk)):
            data = self.incident_payload(**{field: [value]})
            for url in (reverse('incidents:create'), reverse('incidents:edit', args=[self.incident.pk])):
                response = self.client.post(url, data)
                self.assertIn(field, response.context['form'].errors)
        self.assertEqual(self.incident.affected_services.count(), 0)
        self.assertEqual(self.incident.affected_locations.count(), 0)

    def test_lists_and_details_filter_even_corrupt_links(self):
        # Simulate unsupported direct through-table writes to exercise read-side isolation.
        CriticalService.locations.through.objects.create(criticalservice=self.service, location=self.foreign_location)
        Risk.critical_services.through.objects.create(risk=self.other_risk, criticalservice=self.service)
        Incident.affected_services.through.objects.create(incident=self.foreign_incident, criticalservice=self.service)
        response = self.client.get(self.url('detail'))
        for text in (self.foreign_location.name, self.other_risk.title, self.foreign_incident.title):
            self.assertNotContains(response, text)
        self.assertEqual(self.client.get(self.url('list')).context['services'][0].location_count, 1)

    def test_relation_counts_do_not_multiply_joins(self):
        second = Location.objects.create(organization=self.organization, name='Zweiter Standort')
        self.service.locations.add(second)
        ServiceDependency.objects.create(service=self.service, name='Zweite Abhaengigkeit')
        service = self.client.get(self.url('list')).context['services'][0]
        self.assertEqual(service.location_count, 2)
        self.assertEqual(service.dependency_count, 2)

    def test_dashboard_only_counts_current_organization(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['service_counts'], {'active': 1, 'critical': 1})
        self.assertEqual(response.context['dependency_counts'], {'critical': 1, 'single_points': 1})
        self.assertNotContains(response, self.foreign_service.name)

    def test_dashboard_thresholds_and_important_ordering(self):
        other = CriticalService.objects.create(organization=self.organization, name='Hohe Kritikalitaet',
            description='Text', criticality=5, status=CriticalService.Status.INACTIVE)
        ServiceDependency.objects.create(service=self.service, name='Unkritisch', criticality=3, single_point_of_failure=True)
        ServiceDependency.objects.create(service=other, name='Kritisch ohne SPOF', criticality=5)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['service_counts'], {'active': 1, 'critical': 2})
        self.assertEqual(response.context['dependency_counts'], {'critical': 2, 'single_points': 2})
        self.assertEqual(list(response.context['important_services']), [other, self.service])

    def test_organization_switch_changes_dashboard_and_list(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        self.select_organization(self.other_organization)
        self.assertEqual(list(self.client.get(self.url('list')).context['services']), [self.foreign_service])
        self.assertEqual(list(self.client.get('/dashboard/').context['important_services']), [self.foreign_service])

    def test_service_search_filters_and_sorting(self):
        other = CriticalService.objects.create(organization=self.organization, name='Alpha', description='Zweite Beschreibung',
            criticality=5, recovery_priority=5, status=CriticalService.Status.UNDER_REVIEW)
        for query in ({'q': 'Trinkwasser'}, {'q': 'WASSER'}, {'status': 'ACTIVE', 'criticality': 4, 'recovery_priority': 1}):
            self.assertEqual(list(self.client.get(self.url('list'), query).context['services']), [self.service])
        for sort in ('name', 'criticality', 'updated'):
            self.assertEqual(list(self.client.get(self.url('list'), {'sort': sort}).context['services']), [other, self.service])
        self.assertEqual(list(self.client.get(self.url('list'), {'sort': 'recovery_priority'}).context['services']), [self.service, other])
        self.assertEqual(list(self.client.get(self.url('list'), {'sort': 'service_owner__password'}).context['services']), [other, self.service])

    def test_location_search_and_filters(self):
        for query in ({'q': 'Wien'}, {'q': 'Leitstelle'}, {'q': 'Zentrale'}, {'location_type': 'HEADQUARTERS', 'is_active': 'true'}):
            self.assertEqual(list(self.client.get(self.url('location-list'), query).context['locations']), [self.location])
        self.assertEqual(list(self.client.get(self.url('location-list'), {'is_active': 'false'}).context['locations']), [])

    def test_foreign_search_and_get_organization_do_not_leak(self):
        self.assertEqual(list(self.client.get(self.url('list'), {'q': self.foreign_service.name}).context['services']), [])
        self.assertEqual(list(self.client.get(self.url('location-list'), {'q': self.foreign_location.name}).context['locations']), [])
        self.assertEqual(list(self.client.get(self.url('list'), {'organization': self.other_organization.pk}).context['services']), [self.service])

    def test_pagination_preserves_filters(self):
        CriticalService.objects.bulk_create([CriticalService(organization=self.organization, name=f'Wasser {i}', description='Text') for i in range(26)])
        response = self.client.get('/services/?q=Wasser&status=ACTIVE&sort=name')
        self.assertContains(response, '?q=Wasser&amp;status=ACTIVE&amp;sort=name&amp;page=2')
        self.assertEqual(len(self.client.get('/services/?q=Wasser&status=ACTIVE&sort=name&page=2').context['services']), 2)


class ServicesMigrationTests(TransactionTestCase):
    def test_existing_risk_incident_and_freetext_are_unchanged(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [('risks', '0003_residual_risk_controls'), ('incidents', '0001_initial')]
        try:
            executor.migrate([('services', None)] + previous)
            apps = executor.loader.project_state(previous).apps
            user = apps.get_model('accounts', 'User').objects.create(username='legacy-services')
            organization = apps.get_model('organizations', 'Organization').objects.create(name='Bestand')
            risk = apps.get_model('risks', 'Risk').objects.create(organization_id=organization.pk, created_by_id=user.pk,
                title='Bestandsrisiko', likelihood=5, impact=4, residual_likelihood=2, residual_impact=3)
            when = timezone.now()
            incident = apps.get_model('incidents', 'Incident').objects.create(organization_id=organization.pk,
                created_by_id=user.pk, title='Bestandsvorfall', description='Text', impact_description='Text',
                occurred_at=when, detected_at=when, affected_service='Alter Dienst', affected_location='Alter Ort')
            incident.risks.add(risk)
            MigrationExecutor(connection).migrate(latest)
            for old, model in ((risk, Risk), (incident, Incident)):
                current = model.objects.get(pk=old.pk)
                for field in old._meta.concrete_fields:
                    self.assertEqual(getattr(current, field.attname), getattr(old, field.attname))
            current = Incident.objects.get(pk=incident.pk)
            self.assertEqual(list(current.risks.values_list('pk', flat=True)), [risk.pk])
            self.assertFalse(current.affected_services.exists())
            self.assertFalse(current.affected_locations.exists())
            self.assertFalse(Risk.objects.get(pk=risk.pk).critical_services.exists())
            self.assertEqual(CriticalService.objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
