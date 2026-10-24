from django import forms
from django.db.models import Q

from .assessment import DEFAULT_RISK_BANDS, score_expression
from .models import Risk


SORT_ORDERS = {
    'newest': ('-created_at', '-pk'),
    'title': ('title', 'pk'),
    'score_asc': ('score', 'pk'),
    'score_desc': ('-score', '-pk'),
    'updated': ('-updated_at', '-pk'),
}


class RiskFilterForm(forms.Form):
    q = forms.CharField(label='Suche', required=False, max_length=255,
                        widget=forms.TextInput(attrs={'type': 'search'}))
    status = forms.ChoiceField(label='Status', required=False, choices=[
        ('', 'Alle Status'), ('OPEN', 'Offen'), ('IN_PROGRESS', 'In Bearbeitung'), ('CLOSED', 'Geschlossen'),
    ])
    risk_class = forms.ChoiceField(label='Bruttorisikoklasse', required=False,
                                  choices=[('', 'Alle Klassen')] + [(b.code, b.label) for b in DEFAULT_RISK_BANDS])
    residual_risk_class = forms.ChoiceField(label='Restrisikoklasse', required=False,
        choices=[('', 'Alle Klassen')] + [(b.code, b.label) for b in DEFAULT_RISK_BANDS])
    likelihood = forms.ChoiceField(label='Brutto-Wahrscheinlichkeit', required=False,
                                  choices=[('', 'Alle')] + [(v, f'{v} - {label}') for v, label in Risk.Likelihood.choices])
    impact = forms.ChoiceField(label='Brutto-Auswirkung', required=False,
                              choices=[('', 'Alle')] + [(v, f'{v} - {label}') for v, label in Risk.Impact.choices])
    treatment_strategy = forms.ChoiceField(label='Behandlungsstrategie', required=False,
        choices=[('', 'Alle Strategien'), ('none', 'Nicht festgelegt')] + list(Risk.TreatmentStrategy.choices))
    sort = forms.ChoiceField(label='Sortierung', required=False, choices=[
        ('newest', 'Neueste Risiken'), ('title', 'Titel'), ('score_asc', 'Bruttorisikowert aufsteigend'),
        ('score_desc', 'Bruttorisikowert absteigend'), ('updated', 'Zuletzt ge\u00e4ndert'),
    ])

    def __init__(self, data=None, **kwargs):
        data = data.copy() if data is not None else {}
        for name in ('status', 'treatment_strategy'):
            if data.get(name) and data[name] != 'none':
                data[name] = data[name].upper()
        if data.get('sort') not in SORT_ORDERS:
            data['sort'] = 'newest'
        super().__init__(data=data, **kwargs)

    def filter_queryset(self, queryset):
        self.is_valid()
        # Invalid individual filters do not disable other valid filters.
        values = self.cleaned_data
        queryset = queryset.annotate(score=score_expression(), residual_score=score_expression(residual=True))
        if values.get('q'):
            queryset = queryset.filter(Q(title__icontains=values['q']) | Q(description__icontains=values['q']))
        for name in ('status', 'likelihood', 'impact'):
            if values.get(name):
                queryset = queryset.filter(**{name: values[name]})
        if values.get('treatment_strategy'):
            value = values['treatment_strategy']
            queryset = queryset.filter(treatment_strategy='' if value == 'none' else value)
        for field, score in (('risk_class', 'score'), ('residual_risk_class', 'residual_score')):
            band = next((band for band in DEFAULT_RISK_BANDS if band.code == values.get(field)), None)
            if band:
                queryset = queryset.filter(**{f'{score}__gte': band.minimum, f'{score}__lte': band.maximum})
        return queryset.order_by(*SORT_ORDERS[values.get('sort', 'newest')])
