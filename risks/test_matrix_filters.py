from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from core.test_helpers import TenantTestCase
from organizations.models import Membership
from .assessment import calculate_score, classify_score
from .models import Risk


class MatrixTests(TenantTestCase):
    def cells(self, response):
        return {(cell['likelihood'], cell['impact']): cell
                for row in response.context['matrix_rows'] for cell in row['cells']}

    def test_matrix_only_contains_own_risks_and_counts(self):
        response = self.client.get('/risks/matrix/')
        self.assertContains(response, self.risk.title)
        self.assertNotContains(response, self.other_risk.title)
        cells = self.cells(response)
        self.assertEqual(cells[(3, 3)]['count'], 1)
        self.assertEqual(sum(cell['count'] for cell in cells.values()), 1)
        self.assertContains(response, reverse('risks:detail', args=[self.risk.pk]))

    def test_positions_and_central_classification(self):
        low = Risk.objects.create(title='Niedrig', organization=self.organization,
                                  created_by=self.user, likelihood=1, impact=1)
        critical = Risk.objects.create(title='Kritisch', organization=self.organization,
                                       created_by=self.user, likelihood=5, impact=5)
        response = self.client.get('/risks/matrix/')
        cells = self.cells(response)
        self.assertEqual(len(cells), 25)
        self.assertEqual(cells[(1, 1)]['risks'], [low])
        self.assertEqual(cells[(3, 3)]['risks'], [self.risk])
        self.assertEqual(cells[(5, 5)]['risks'], [critical])
        for (likelihood, impact), cell in cells.items():
            self.assertEqual(cell['score'], calculate_score(likelihood, impact))
            self.assertEqual(cell['band'], classify_score(cell['score']))
        self.assertEqual([row['likelihood'] for row in response.context['matrix_rows']], [5, 4, 3, 2, 1])

    def test_viewer_has_access(self):
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.get('/risks/matrix/').status_code, 200)

    def test_anonymous_redirect(self):
        self.client.logout()
        self.assertRedirects(self.client.get('/risks/matrix/'), '/login/?next=/risks/matrix/')

    def test_inactive_membership_denied(self):
        self.membership.is_active = False
        self.membership.save()
        response = self.client.get('/risks/matrix/', follow=True)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, self.risk.title, status_code=403)

    def test_membership_switch_changes_matrix(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        self.assertRedirects(self.client.get('/risks/matrix/'), '/organizations/select/')
        self.select_organization(self.other_organization)
        response = self.client.get('/risks/matrix/')
        self.assertEqual(self.cells(response)[(3, 3)]['risks'], [self.other_risk])
        self.assertNotContains(response, self.risk.title)

    def test_get_organization_parameter_is_ignored(self):
        response = self.client.get('/risks/matrix/', {'organization': self.other_organization.pk})
        self.assertEqual(self.cells(response)[(3, 3)]['risks'], [self.risk])

    def test_empty_matrix_has_25_zero_cells(self):
        self.risk.delete()
        response = self.client.get('/risks/matrix/')
        self.assertEqual(len(self.cells(response)), 25)
        self.assertEqual(sum(cell['count'] for cell in self.cells(response).values()), 0)

    def test_risk_titles_are_escaped(self):
        self.risk.title = '<script>alert(1)</script>'
        self.risk.save()
        response = self.client.get('/risks/matrix/')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>')

    def test_dashboard_links_matrix(self):
        self.assertContains(self.client.get('/dashboard/'), 'Risikomatrix anzeigen')


class RegisterFilterTests(TenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.low = Risk.objects.create(title='Alpha', description='Wasserleitung',
            organization=cls.organization, created_by=cls.user, likelihood=1, impact=1,
            status=Risk.Status.CLOSED, treatment_strategy=Risk.TreatmentStrategy.ACCEPT)
        cls.critical = Risk.objects.create(title='Zulu Strom', description='Notstromversorgung',
            organization=cls.organization, created_by=cls.user, likelihood=5, impact=5,
            treatment_strategy=Risk.TreatmentStrategy.REDUCE)
        cls.high = Risk.objects.create(title='Beta', description='Lieferkette',
            organization=cls.organization, created_by=cls.user, likelihood=4, impact=4,
            status=Risk.Status.IN_PROGRESS, treatment_strategy=Risk.TreatmentStrategy.TRANSFER)

    def results(self, **params):
        response = self.client.get('/risks/', params)
        self.assertEqual(response.status_code, 200)
        return list(response.context['risks'])

    def test_title_search(self):
        self.assertCountEqual(self.results(q='STROM'), [self.risk, self.critical])

    def test_description_search(self):
        self.assertEqual(self.results(q='Wasserleitung'), [self.low])

    def test_search_does_not_find_foreign_risk(self):
        self.assertEqual(self.results(q=self.other_risk.title), [])

    def test_status_filter(self):
        self.assertEqual(self.results(status='closed'), [self.low])
        self.assertEqual(self.results(status='IN_PROGRESS'), [self.high])

    def test_class_filters(self):
        for code, risk in [('low', self.low), ('medium', self.risk), ('high', self.high), ('critical', self.critical)]:
            self.assertEqual(self.results(risk_class=code), [risk])

    def test_likelihood_filter(self):
        self.assertEqual(self.results(likelihood=5), [self.critical])

    def test_impact_filter(self):
        self.assertEqual(self.results(impact=1), [self.low])

    def test_treatment_filter(self):
        self.assertEqual(self.results(treatment_strategy='reduce'), [self.critical])
        self.assertEqual(self.results(treatment_strategy='none'), [self.risk])

    def test_combined_filters(self):
        self.assertEqual(self.results(q='strom', status='open', risk_class='critical',
                         likelihood=5, impact=5, treatment_strategy='REDUCE'), [self.critical])
        self.assertEqual(self.results(status='closed', risk_class='critical'), [])

    def test_score_sorting(self):
        expected = [self.low, self.risk, self.high, self.critical]
        self.assertEqual(self.results(sort='score_asc'), expected)
        self.assertEqual(self.results(sort='score_desc'), list(reversed(expected)))

    def test_title_newest_and_updated_sorting(self):
        self.assertEqual(self.results(sort='title'), [self.low, self.high, self.risk, self.critical])
        self.assertEqual(self.results(sort='newest'), [self.high, self.critical, self.low, self.risk])
        Risk.objects.filter(pk=self.risk.pk).update(updated_at=timezone.now())
        self.assertEqual(self.results(sort='updated')[0], self.risk)

    def test_invalid_sort_falls_back(self):
        for value in ('invalid', 'organization__name', '-created_by__password', 'title; DROP TABLE risks_risk'):
            self.assertEqual(self.results(sort=value), self.results(sort='newest'))

    def test_invalid_filters_preserve_valid_filters(self):
        self.assertEqual(self.results(status='CLOSED', likelihood='invalid', impact=100,
                                     risk_class='invalid', treatment_strategy='invalid'), [self.low])

    def test_manipulated_organization_cannot_change_scope(self):
        for params in ({'organization': self.other_organization.pk},
                       {'organization_id': self.other_organization.pk, 'sort': 'score_desc'},
                       {'status': 'OPEN', 'risk_class': 'medium'}):
            self.assertNotIn(self.other_risk, self.results(**params))

    def test_other_active_membership_remains_scoped(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        self.select_organization(self.organization)
        self.assertNotIn(self.other_risk, self.results())
        self.select_organization(self.other_organization)
        self.assertEqual(self.results(sort='score_desc'), [self.other_risk])

    def test_pagination_preserves_filters(self):
        Risk.objects.bulk_create([Risk(title=f'Strom {i}', organization=self.organization,
                                 created_by=self.user) for i in range(26)])
        response = self.client.get('/risks/', {'q': 'Strom', 'status': 'OPEN', 'sort': 'title'})
        self.assertContains(response, '?q=Strom&amp;status=OPEN&amp;sort=title&amp;page=2')
        second = self.client.get('/risks/', {'q': 'Strom', 'status': 'OPEN', 'sort': 'title', 'page': 2})
        self.assertEqual(len(second.context['risks']), 3)
        self.assertNotContains(second, self.other_risk.title)

    def test_detail_edit_and_save_preserve_register_query(self):
        query = urlencode({'q': 'Strom', 'sort': 'score_desc'})
        detail = reverse('risks:detail', args=[self.risk.pk])
        edit = reverse('risks:edit', args=[self.risk.pk]) + '?' + urlencode({'register': query})
        response = self.client.get(detail, {'register': query})
        self.assertContains(response, '/risks/?q=Strom&amp;sort=score_desc')
        response = self.client.post(edit, self.risk_payload(edit))
        self.assertRedirects(response, detail + '?' + urlencode({'register': query}))

    def test_empty_results_and_reset_link(self):
        response = self.client.get('/risks/', {'q': 'not-found'})
        self.assertEqual(response.context['paginator'].count, 0)
        self.assertContains(response, 'Filter zur&uuml;cksetzen')

    def test_viewer_can_search_and_filter(self):
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.results(risk_class='critical'), [self.critical])

    def test_search_input_is_escaped(self):
        response = self.client.get('/risks/', {'q': '<script>alert(1)</script>'})
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')
