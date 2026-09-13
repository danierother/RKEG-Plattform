from django import forms
from django.core import signing
from django.contrib.auth import get_user_model

from .assessment import calculate_score, classify_score
from .models import Risk, RiskMeasure


class RiskForm(forms.ModelForm):
    organization_context = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Risk
        fields = ('title', 'description', 'status', 'likelihood', 'impact', 'treatment_strategy')
        labels = {'title': 'Titel', 'description': 'Beschreibung', 'status': 'Status',
                  'likelihood': 'Eintrittswahrscheinlichkeit', 'impact': 'Auswirkung',
                  'treatment_strategy': 'Behandlungsstrategie'}
        widgets = {'description': forms.Textarea(attrs={'rows': 7})}

    def __init__(self, *args, organization, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_context = {'organization': organization.pk, 'user': user.pk}
        self.fields['organization_context'].initial = signing.dumps(
            self.expected_context, salt='risk-form-organization',
        )
        self.fields['status'].choices = [
            (Risk.Status.OPEN, 'Offen'),
            (Risk.Status.IN_PROGRESS, 'In Bearbeitung'),
            (Risk.Status.CLOSED, 'Geschlossen'),
        ]
        for name in ('likelihood', 'impact'):
            self.fields[name].choices = [(value, f'{value} - {label}')
                                         for value, label in self.fields[name].choices]

    @property
    def assessment(self):
        try:
            score = calculate_score(int(self['likelihood'].value()), int(self['impact'].value()))
        except (ValueError, TypeError):
            return None
        return {'score': score, 'band': classify_score(score)}

    def clean_organization_context(self):
        value = self.cleaned_data['organization_context']
        try:
            context = signing.loads(value, salt='risk-form-organization')
        except signing.BadSignature:
            context = None
        if context != self.expected_context:
            raise forms.ValidationError(
                'Der Organisationskontext hat sich ge\u00e4ndert. Bitte laden Sie das Formular neu.'
            )
        return value


class RiskMeasureForm(forms.ModelForm):
    class Meta:
        model = RiskMeasure
        fields = ('title', 'description', 'status', 'responsible_user', 'due_date')
        labels = {'title': 'Titel', 'description': 'Beschreibung', 'status': 'Status',
                  'responsible_user': 'Verantwortlich', 'due_date': 'F\u00e4llig am'}
        widgets = {'description': forms.Textarea(attrs={'rows': 5}),
                   'due_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})}

    def __init__(self, *args, risk, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.risk = risk
        self.instance.organization = risk.organization
        self.fields['responsible_user'].queryset = get_user_model().objects.filter(
            is_active=True, memberships__organization=risk.organization,
            memberships__is_active=True,
        ).order_by('username')
