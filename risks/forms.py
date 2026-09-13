from django import forms
from django.core import signing

from .models import Risk


class RiskForm(forms.ModelForm):
    organization_context = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Risk
        fields = ('title', 'description', 'status')
        labels = {'title': 'Titel', 'description': 'Beschreibung', 'status': 'Status'}
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
