from django import forms
from django.db.models import Q

from .models import Incident


SORT_ORDERS = {
    'newest': ('-created_at', '-pk'),
    'updated': ('-updated_at', '-pk'),
    'occurred': ('-occurred_at', '-pk'),
    'title': ('title', 'pk'),
    'severity_desc': ('-severity', '-pk'),
    'severity_asc': ('severity', 'pk'),
}


class IncidentFilterForm(forms.Form):
    q = forms.CharField(label='Suche', required=False, max_length=255,
                        widget=forms.TextInput(attrs={'type': 'search'}))
    status = forms.ChoiceField(label='Status', required=False, choices=[('', 'Alle Status')] + list(Incident.Status.choices))
    severity = forms.ChoiceField(label='Schweregrad', required=False,
        choices=[('', 'Alle Schweregrade')] + [(v, f'{v} - {label}') for v, label in Incident.Severity.choices])
    incident_type = forms.ChoiceField(label='Vorfallart', required=False,
        choices=[('', 'Alle Vorfallarten')] + list(Incident.IncidentType.choices))
    reporting_status = forms.ChoiceField(label='Meldepr\u00fcfung', required=False,
        choices=[('', 'Alle Pr\u00fcfstatus')] + list(Incident.ReportingStatus.choices))
    sort = forms.ChoiceField(label='Sortierung', required=False, choices=[
        ('newest', 'Neueste Vorf\u00e4lle'), ('updated', 'Zuletzt ge\u00e4ndert'),
        ('occurred', 'Ereigniszeit'), ('title', 'Titel'),
        ('severity_desc', 'Schweregrad absteigend'), ('severity_asc', 'Schweregrad aufsteigend'),
    ])

    def __init__(self, data=None, **kwargs):
        data = data.copy() if data is not None else {}
        for name in ('status', 'incident_type', 'reporting_status'):
            if data.get(name):
                data[name] = data[name].upper()
        if data.get('sort') not in SORT_ORDERS:
            data['sort'] = 'newest'
        super().__init__(data=data, **kwargs)

    def filter_queryset(self, queryset):
        self.is_valid()
        values = self.cleaned_data
        if values.get('q'):
            queryset = queryset.filter(Q(title__icontains=values['q']) | Q(description__icontains=values['q'])
                                       | Q(impact_description__icontains=values['q']))
        for name in ('status', 'severity', 'incident_type', 'reporting_status'):
            if values.get(name):
                queryset = queryset.filter(**{name: values[name]})
        return queryset.order_by(*SORT_ORDERS[values.get('sort', 'newest')])
