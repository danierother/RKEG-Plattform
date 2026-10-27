from django import forms

from .models import Organization


class OrganizationSelectionForm(forms.Form):
    organization = forms.ModelChoiceField(
        label='Organisation', queryset=Organization.objects.none(), empty_label='Bitte ausw\u00e4hlen',
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organization'].queryset = Organization.objects.filter(
            memberships__user=user, memberships__is_active=True,
        ).order_by('name', 'pk')


class OrganizationRKEGForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ('rkeg_classified', 'rkeg_classification_reference', 'rkeg_reporting_obligation_start_date')
        widgets = {'rkeg_reporting_obligation_start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def clean(self):
        data = super().clean()
        if data.get('rkeg_classified') and not data.get('rkeg_classification_reference', '').strip():
            self.add_error('rkeg_classification_reference', 'Bitte den behoerdlichen Einstufungsbescheid dokumentieren.')
        return data
