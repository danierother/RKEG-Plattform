from django import forms

from .forms import datetime_widget
from .models import Incident, IncidentReport, IncidentRKEGAssessment, IncidentServiceImpact
from .rkeg_reporting import FACT_FIELDS


class ReportingFactsForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = ('rkeg_awareness_at',) + FACT_FIELDS
        widgets = {name: datetime_widget() for name in ('rkeg_awareness_at', 'disruption_started_at', 'disruption_ended_at')}


class ServiceImpactForm(forms.ModelForm):
    class Meta:
        model = IncidentServiceImpact
        fields = FACT_FIELDS
        widgets = {name: datetime_widget() for name in ('disruption_started_at', 'disruption_ended_at')}

    def __init__(self, *args, incident, service, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.incident = incident
        self.instance.organization = incident.organization
        self.instance.service = service


class IncidentReportForm(forms.ModelForm):
    class Meta:
        model = IncidentReport
        fields = ('report_type', 'status', 'submitted_at', 'incident_type_description', 'suspected_cause',
            'confirmed_cause', 'consequences', 'measures_taken', 'affected_critical_infrastructure',
            'cross_border_information', 'additional_information')
        widgets = {'submitted_at': datetime_widget()}

    def __init__(self, *args, incident, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.incident = incident
        self.instance.organization = incident.organization
        if not self.instance.pk:
            self.instance.created_by = user
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3


class AssessmentForm(forms.Form):
    override_result = forms.ChoiceField(label='Zusaetzliche manuelle Bewertung', required=False,
        choices=[('', 'Nur automatische Bewertung dokumentieren')] + list(IncidentRKEGAssessment.Result.choices))
    override_reason = forms.CharField(label='Begruendung der manuellen Bewertung', required=False,
                                      widget=forms.Textarea(attrs={'rows': 4}))

    def clean(self):
        data = super().clean()
        if data.get('override_result') and not data.get('override_reason', '').strip():
            self.add_error('override_reason', 'Eine manuelle Bewertung muss begruendet werden.')
        return data
