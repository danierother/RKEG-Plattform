from django import forms
from django.contrib.auth import get_user_model
from django.core import signing

from risks.models import Risk
from .models import Incident, IncidentAction, IncidentEvent


def datetime_widget():
    return forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})


def responsible_users(organization):
    return get_user_model().objects.filter(is_active=True, memberships__organization=organization,
                                          memberships__is_active=True).order_by('username')


class IncidentForm(forms.ModelForm):
    organization_context = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Incident
        fields = ('title', 'description', 'occurred_at', 'detected_at', 'status', 'severity',
                  'incident_type', 'responsible_user', 'affected_service', 'affected_location',
                  'impact_description', 'immediate_actions', 'suspected_reportable', 'reporting_status', 'risks')
        widgets = {
            'occurred_at': datetime_widget(), 'detected_at': datetime_widget(),
            'description': forms.Textarea(attrs={'rows': 4}),
            'impact_description': forms.Textarea(attrs={'rows': 4}),
            'immediate_actions': forms.Textarea(attrs={'rows': 4}),
            'risks': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, organization, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        if not self.instance.pk:
            self.instance.created_by = user
        self.expected_context = {'organization': organization.pk, 'user': user.pk}
        self.fields['organization_context'].initial = signing.dumps(self.expected_context, salt='incident-form')
        self.fields['responsible_user'].queryset = responsible_users(organization)
        self.fields['risks'].queryset = Risk.objects.filter(organization=organization).order_by('title', 'pk')
        self.fields['severity'].choices = [(value, f'{value} - {label}') for value, label in Incident.Severity.choices]

    def clean_organization_context(self):
        value = self.cleaned_data['organization_context']
        try:
            context = signing.loads(value, salt='incident-form')
        except signing.BadSignature:
            context = None
        if context != self.expected_context:
            raise forms.ValidationError('Der Organisationskontext hat sich geaendert. Bitte laden Sie das Formular neu.')
        return value

    @property
    def sections(self):
        sections = (
            ('Vorfall', ('title', 'description', 'status', 'severity', 'incident_type', 'responsible_user')),
            ('Zeit', ('occurred_at', 'detected_at')),
            ('Auswirkungen', ('impact_description', 'affected_service', 'affected_location', 'immediate_actions')),
            ('Meldepflichtpr\u00fcfung', ('suspected_reportable', 'reporting_status')),
            ('Verkn\u00fcpfte Risiken', ('risks',)),
        )
        return [{'title': title, 'fields': [self[name] for name in names]} for title, names in sections]


class IncidentEventForm(forms.ModelForm):
    class Meta:
        model = IncidentEvent
        fields = ('event_time', 'event_type', 'description')
        widgets = {'event_time': datetime_widget(), 'description': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, incident, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.incident = incident
        self.instance.organization = incident.organization
        self.instance.created_by = user


class IncidentActionForm(forms.ModelForm):
    class Meta:
        model = IncidentAction
        fields = ('title', 'description', 'status', 'responsible_user', 'due_date', 'completed_at')
        widgets = {'description': forms.Textarea(attrs={'rows': 5}),
                   'due_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
                   'completed_at': datetime_widget()}

    def __init__(self, *args, incident, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.incident = incident
        self.instance.organization = incident.organization
        self.fields['responsible_user'].queryset = responsible_users(incident.organization)
