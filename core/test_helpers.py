from django.contrib.auth import get_user_model
from django.test import TestCase

from organizations.mixins import ORGANIZATION_SESSION_KEY
from organizations.models import Membership, Organization
from risks.models import Risk


class TenantTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('member', first_name='Alex', last_name='Muster')
        cls.other_user = get_user_model().objects.create_user('other-member')
        cls.organization = Organization.objects.create(name='Alpen Infrastruktur')
        cls.other_organization = Organization.objects.create(name='Fremde Organisation')
        cls.membership = Membership.objects.create(
            user=cls.user, organization=cls.organization, role=Membership.Role.ADMIN,
        )
        cls.risk = Risk.objects.create(
            title='Stromausfall', description='Versorgung unterbrochen.',
            organization=cls.organization, created_by=cls.user,
        )
        cls.other_risk = Risk.objects.create(
            title='Vertrauliches Fremdrisiko', organization=cls.other_organization,
            created_by=cls.other_user,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def select_organization(self, organization):
        session = self.client.session
        session[ORGANIZATION_SESSION_KEY] = organization.pk
        session.save()

    def set_role(self, role):
        self.membership.role = role
        self.membership.save(update_fields=['role'])

    def risk_payload(self, url, **overrides):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = {
            'title': 'Neues Risiko', 'description': 'Beschreibung', 'status': Risk.Status.OPEN,
            'organization_context': response.context['form']['organization_context'].value(),
        }
        data.update(overrides)
        return data
