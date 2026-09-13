from dataclasses import dataclass

from django.db.models import F


@dataclass(frozen=True)
class RiskBand:
    code: str
    label: str
    minimum: int
    maximum: int

    def __str__(self):
        return self.label


DEFAULT_RISK_BANDS = (
    RiskBand('low', 'Niedrig', 1, 4),
    RiskBand('medium', 'Mittel', 5, 9),
    RiskBand('high', 'Hoch', 10, 16),
    RiskBand('critical', 'Kritisch', 17, 25),
)


def score_expression():
    return F('likelihood') * F('impact')


def calculate_score(likelihood, impact):
    if any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5
           for value in (likelihood, impact)):
        raise ValueError('Bewertungen muessen ganze Zahlen zwischen 1 und 5 sein.')
    return likelihood * impact


def classify_score(score, bands=DEFAULT_RISK_BANDS):
    if type(score) is not int:
        raise ValueError('Der Risikowert muss eine ganze Zahl sein.')
    for band in bands:
        if band.minimum <= score <= band.maximum:
            return band
    raise ValueError('Der Risikowert liegt ausserhalb der Bewertungsskala.')
