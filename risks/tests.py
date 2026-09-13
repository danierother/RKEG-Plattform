from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from organizations.models import Organization
from .models import Risk


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
