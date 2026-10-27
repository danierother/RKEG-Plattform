from django import forms
from django.db.models import Q

from .models import CriticalService, Location


SERVICE_SORTS = {'name': ('name', 'pk'), 'criticality': ('-criticality', 'name', 'pk'),
                 'recovery_priority': ('recovery_priority', 'name', 'pk'), 'updated': ('-updated_at', '-pk')}


class LocationFilterForm(forms.Form):
    q = forms.CharField(label='Suche', required=False, max_length=255, widget=forms.TextInput(attrs={'type': 'search'}))
    location_type = forms.ChoiceField(label='Typ', required=False, choices=[('', 'Alle Typen')] + list(Location.LocationType.choices))
    is_active = forms.ChoiceField(label='Aktivstatus', required=False, choices=[('', 'Alle'), ('true', 'Aktiv'), ('false', 'Inaktiv')])

    def filter_queryset(self, queryset):
        self.is_valid()
        values = self.cleaned_data
        if values.get('q'):
            queryset = queryset.filter(Q(name__icontains=values['q']) | Q(city__icontains=values['q']) | Q(description__icontains=values['q']))
        if values.get('location_type'):
            queryset = queryset.filter(location_type=values['location_type'])
        if values.get('is_active'):
            queryset = queryset.filter(is_active=values['is_active'] == 'true')
        return queryset.order_by('name', 'pk')


class ServiceFilterForm(forms.Form):
    q = forms.CharField(label='Suche', required=False, max_length=255, widget=forms.TextInput(attrs={'type': 'search'}))
    status = forms.ChoiceField(label='Status', required=False, choices=[('', 'Alle Status')] + list(CriticalService.Status.choices))
    criticality = forms.ChoiceField(label='Kritikalit\u00e4t', required=False, choices=[('', 'Alle')] + list(CriticalService.Criticality.choices))
    recovery_priority = forms.ChoiceField(label='Recovery Priority', required=False, choices=[('', 'Alle')] + list(CriticalService.RecoveryPriority.choices))
    sort = forms.ChoiceField(label='Sortierung', required=False, choices=[('name', 'Name'), ('criticality', 'Kritikalit\u00e4t absteigend'),
        ('recovery_priority', 'Recovery Priority aufsteigend'), ('updated', 'Zuletzt ge\u00e4ndert')])

    def __init__(self, data=None, **kwargs):
        data = data.copy() if data is not None else {}
        if data.get('sort') not in SERVICE_SORTS:
            data['sort'] = 'name'
        super().__init__(data=data, **kwargs)

    def filter_queryset(self, queryset):
        self.is_valid()
        values = self.cleaned_data
        if values.get('q'):
            queryset = queryset.filter(Q(name__icontains=values['q']) | Q(description__icontains=values['q']))
        for name in ('status', 'criticality', 'recovery_priority'):
            if values.get(name):
                queryset = queryset.filter(**{name: values[name]})
        return queryset.order_by(*SERVICE_SORTS[values.get('sort', 'name')])
