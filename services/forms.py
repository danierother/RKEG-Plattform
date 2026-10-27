from django import forms
from django.contrib.auth import get_user_model
from django.core import signing

from .models import CriticalService, Location, ServiceDependency
from incidents.rkeg_rules import RULE_BY_CODE, SECTORS, SERVICE_CHOICES


class OrganizationForm(forms.ModelForm):
    organization_context = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, organization, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        self.expected_context = {'organization': organization.pk, 'user': user.pk}
        self.fields['organization_context'].initial = signing.dumps(self.expected_context, salt='services-form')

    def clean_organization_context(self):
        value = self.cleaned_data['organization_context']
        try:
            context = signing.loads(value, salt='services-form')
        except signing.BadSignature:
            context = None
        if context != self.expected_context:
            raise forms.ValidationError('Der Organisationskontext hat sich geaendert. Bitte laden Sie das Formular neu.')
        return value


class LocationForm(OrganizationForm):
    class Meta:
        model = Location
        fields = ('name', 'description', 'address_line', 'postal_code', 'city', 'country', 'location_type', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}


class CriticalServiceForm(OrganizationForm):
    rkeg_sector = forms.ChoiceField(label='RKEG-Sektor', required=False, choices=[('', 'Nicht zugeordnet')] + list(SECTORS))
    rkeg_service_code = forms.ChoiceField(label='Wesentlicher Dienst laut Bescheid', required=False,
                                        choices=[('', 'Nicht zugeordnet')] + SERVICE_CHOICES)
    class Meta:
        model = CriticalService
        fields = ('name', 'description', 'service_owner', 'status', 'criticality', 'recovery_priority',
                  'maximum_tolerable_downtime', 'recovery_time_objective', 'locations', 'notes',
                  'rkeg_sector', 'rkeg_service_code', 'rkeg_service_reference')
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'notes': forms.Textarea(attrs={'rows': 4}),
                   'locations': forms.CheckboxSelectMultiple(),
                   'maximum_tolerable_downtime': forms.TextInput(attrs={'placeholder': '1 00:00:00'}),
                   'recovery_time_objective': forms.TextInput(attrs={'placeholder': '04:00:00'})}
        labels = {'maximum_tolerable_downtime': 'MTD (Tage HH:MM:SS)',
                  'recovery_time_objective': 'RTO (Tage HH:MM:SS)'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.instance.organization
        self.fields['locations'].queryset = Location.objects.filter(organization=organization).order_by('name', 'pk')
        self.fields['service_owner'].queryset = get_user_model().objects.filter(
            is_active=True, memberships__organization=organization, memberships__is_active=True,
        ).order_by('username')
        for field in ('criticality', 'recovery_priority'):
            self.fields[field].choices = [(value, f'{value} - {label}') for value, label in self.fields[field].choices]

    def clean(self):
        data = super().clean()
        rule = RULE_BY_CODE.get(data.get('rkeg_service_code'))
        if rule and rule.sector != data.get('rkeg_sector'):
            self.add_error('rkeg_service_code', 'Der Dienst gehoert nicht zum ausgewaehlten Sektor.')
        self.instance.rkeg_subsector = rule.subsector if rule else ''
        return data


class ServiceDependencyForm(forms.ModelForm):
    class Meta:
        model = ServiceDependency
        fields = ('name', 'description', 'dependency_type', 'criticality', 'supplier_name', 'internal_external',
                  'single_point_of_failure', 'contingency_available', 'notes')
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, service, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.service = service
        self.instance.organization = service.organization
        self.fields['criticality'].choices = [(value, f'{value} - {label}') for value, label in ServiceDependency.Criticality.choices]
