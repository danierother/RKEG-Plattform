from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from incidents.models import Incident, IncidentAction, IncidentRKEGAssessment
from risks.models import Risk, RiskMeasure
from risks.assessment import DEFAULT_RISK_BANDS
from services.models import CriticalService


class PeriodForm(forms.Form):
    date_from = forms.DateField(label='Von', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Bis', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('Der Beginn darf nicht nach dem Ende liegen.')
        return data


class RiskReportForm(PeriodForm):
    risk_class = forms.ChoiceField(label='Bruttorisikoklasse', required=False,
        choices=[('', 'Alle')] + [(band.code, band.label) for band in DEFAULT_RISK_BANDS])
    residual_risk_class = forms.ChoiceField(label='Restrisikoklasse', required=False,
        choices=[('', 'Alle')] + [(band.code, band.label) for band in DEFAULT_RISK_BANDS])
    status = forms.ChoiceField(label='Status', required=False, choices=[('', 'Alle')] + list(Risk.Status.choices))
    service = forms.ModelChoiceField(label='Kritische Dienstleistung', required=False, queryset=CriticalService.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['service'].queryset = CriticalService.objects.filter(organization=self.organization).order_by('name', 'pk')


class ActionReportForm(PeriodForm):
    type = forms.ChoiceField(label='Typ', required=False, choices=[('', 'Alle'), ('risk', 'Risikomassnahme'), ('incident', 'Vorfallmassnahme')])
    status = forms.ChoiceField(label='Status', required=False, choices=[('', 'Alle')] +
        list(dict(list(RiskMeasure.Status.choices) + list(IncidentAction.Status.choices)).items()))
    responsible_user = forms.ModelChoiceField(label='Verantwortlich', required=False, queryset=get_user_model().objects.none())
    overdue = forms.ChoiceField(label='Ueberfaellig', required=False, choices=[('', 'Alle'), ('yes', 'Ja'), ('no', 'Nein')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsible_user'].queryset = get_user_model().objects.filter(
            Q(memberships__organization=self.organization) |
            Q(risk_measures__organization=self.organization, risk_measures__risk__organization=self.organization) |
            Q(incident_actions__organization=self.organization, incident_actions__incident__organization=self.organization)
        ).distinct().order_by('username')


class IncidentReportFilterForm(PeriodForm):
    status = forms.ChoiceField(label='Status', required=False, choices=[('', 'Alle')] + list(Incident.Status.choices))
    severity = forms.ChoiceField(label='Schweregrad', required=False, choices=[('', 'Alle')] + list(Incident.Severity.choices))
    incident_type = forms.ChoiceField(label='Vorfallart', required=False, choices=[('', 'Alle')] + list(Incident.IncidentType.choices))
    rkeg_result = forms.ChoiceField(label='RKEG-Ergebnis (automatisch)', required=False,
        choices=[('', 'Alle')] + list(IncidentRKEGAssessment.Result.choices))
