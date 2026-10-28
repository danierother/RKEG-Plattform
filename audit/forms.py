from django import forms
from django.contrib.auth import get_user_model
from .models import AuditEvent
from .services import FIELDS


class AuditFilterForm(forms.Form):
    q = forms.CharField(label='Suche', required=False, max_length=255)
    date_from = forms.DateField(label='Von', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Bis', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    actor = forms.ModelChoiceField(label='Benutzer', required=False, queryset=get_user_model().objects.none())
    object_type = forms.ChoiceField(label='Objekttyp', required=False,
        choices=[('', 'Alle')] + [(key, key) for key in FIELDS])
    action = forms.ChoiceField(label='Aktion', required=False, choices=[('', 'Alle')] + list(AuditEvent.Action.choices))

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['actor'].queryset = get_user_model().objects.filter(
            pk__in=AuditEvent.objects.filter(organization=organization).values('actor_id')).order_by('username')

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('Der Beginn darf nicht nach dem Ende liegen.')
        return data
