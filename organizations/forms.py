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
