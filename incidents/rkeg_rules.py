"""RKEV BGBl. II 91/2026, verified against the promulgated RIS text.

Codes are internal identifiers, not official authority interchange codes.
Only incident thresholds are represented, never classification thresholds.
"""
from dataclasses import dataclass
from datetime import date

RULE_VERSION = 'RKEV-2026-04-15/v1'
EFFECTIVE_FROM = date(2026, 4, 15)
SOURCE = 'https://www.ris.bka.gv.at/Dokumente/BgblAuth/BGBLA_2026_II_91/BGBLA_2026_II_91.html'
SECTORS = (
    ('ENERGY', 'Energie'), ('TRANSPORT', 'Verkehr'), ('HEALTH', 'Gesundheit'),
    ('WATER', 'Trinkwasser'), ('WASTEWATER', 'Abwasser'), ('PUBLIC', 'Oeffentliche Verwaltung'),
    ('SPACE', 'Weltraum'), ('FOOD', 'Lebensmittel'), ('BANKING', 'Bankwesen'),
    ('FINANCIAL', 'Finanzmarktinfrastrukturen'), ('DIGITAL', 'Digitale Infrastruktur'),
)
EXEMPT_SECTORS = {'BANKING', 'FINANCIAL', 'DIGITAL'}


@dataclass(frozen=True)
class Rule:
    sector: str
    subsector: str
    service_code: str
    label: str
    threshold_type: str
    threshold_value: int | None
    unit: str
    legal_reference: str
    effective_from: date = EFFECTIVE_FROM


def rule(sector, subsector, code, label, value, reference, kind='HOURS'):
    units = {'HOURS': 'Stunden', 'USER_HOURS': 'Nutzerstunden',
             'METER_HOURS': 'Zaehlpunktstunden', 'SPECIAL': 'Sonderkriterium'}
    return Rule(sector, subsector, code, label, kind, value, units[kind], 'RKEV ' + reference)


RULES = (
    rule('ENERGY', 'Strom', 'E_SUPPLY', 'Elektrizitaetsversorgung', 250000, '§ 3 Abs. 2 Z 1 lit. a', 'METER_HOURS'),
    rule('ENERGY', 'Strom', 'E_DISTRIBUTION', 'Elektrizitaetsverteilernetz', 250000, '§ 3 Abs. 2 Z 1 lit. a', 'METER_HOURS'),
    rule('ENERGY', 'Strom', 'E_TRANSMISSION', 'Elektrizitaetsuebertragungsnetz', 2, '§ 3 Abs. 2 Z 1 lit. b'),
    rule('ENERGY', 'Strom', 'E_GENERATION', 'Elektrizitaetserzeugung', 4, '§ 3 Abs. 2 Z 1 lit. c'),
    rule('ENERGY', 'Strom', 'E_MARKET', 'Dienste nominierter Strommarktbetreiber', None, '§ 3 Abs. 2 Z 1 lit. d', 'SPECIAL'),
    rule('ENERGY', 'Strom', 'E_DEMAND', 'Laststeuerung', 24, '§ 3 Abs. 2 Z 1 lit. e'),
    rule('ENERGY', 'Strom', 'E_AGGREGATION', 'Aggregierung von Elektrizitaet', 24, '§ 3 Abs. 2 Z 1 lit. f'),
    rule('ENERGY', 'Strom', 'E_STORAGE', 'Energiespeicherung', 12, '§ 3 Abs. 2 Z 1 lit. g'),
    rule('ENERGY', 'Fernwaerme / Fernkaelte', 'HEAT', 'Fernwaerme / Fernkaelte', 250000, '§ 3 Abs. 2 Z 2', 'USER_HOURS'),
    *(rule('ENERGY', 'Erdoel', code, label, 24, '§ 3 Abs. 2 Z 3') for code, label in (
        ('OIL_PIPELINE', 'Fernleitung von Erdoel'), ('OIL_PRODUCTION', 'Produktion von Erdoel'),
        ('OIL_REFINING', 'Raffination / Aufbereitung von Erdoel'), ('OIL_STORAGE', 'Lagerung von Erdoel'),
        ('OIL_RESERVES', 'Verwaltung von Erdoelvorraeten'))),
    rule('ENERGY', 'Erdgas', 'GAS_SUPPLY', 'Lieferung von Erdgas', 12, '§ 3 Abs. 2 Z 4 lit. a'),
    rule('ENERGY', 'Erdgas', 'GAS_DISTRIBUTION', 'Verteilung von Erdgas', 100000, '§ 3 Abs. 2 Z 4 lit. b', 'METER_HOURS'),
    rule('ENERGY', 'Erdgas', 'GAS_STORAGE', 'Speicherung von Erdgas', 12, '§ 3 Abs. 2 Z 4 lit. a'),
    *(rule('ENERGY', 'Erdgas', code, label, 24, '§ 3 Abs. 2 Z 4 lit. c') for code, label in (
        ('GAS_PIPELINE', 'Fernleitung von Erdgas'), ('GAS_LNG', 'LNG-System'), ('GAS_EXTRACTION', 'Gewinnung von Erdgas'),
        ('GAS_PURCHASE', 'Ankauf von Erdgas'), ('GAS_REFINING', 'Raffination / Aufbereitung von Erdgas'))),
    *(rule('ENERGY', 'Wasserstoff', code, label, 24, '§ 3 Abs. 2 Z 5') for code, label in (
        ('H2_PRODUCTION', 'Erzeugung von Wasserstoff'), ('H2_STORAGE', 'Speicherung von Wasserstoff'),
        ('H2_PIPELINE', 'Fernleitung von Wasserstoff'))),
    rule('TRANSPORT', 'Luftfahrt', 'AIR_COMMERCIAL', 'Gewerbliche Luftverkehrsdienste', 12, '§ 4 Abs. 2 Z 1 lit. a'),
    rule('TRANSPORT', 'Luftfahrt', 'AIRPORT', 'Flughafen / Flughafennetz', 12, '§ 4 Abs. 2 Z 1 lit. a'),
    rule('TRANSPORT', 'Luftfahrt', 'AIR_CONTROL', 'Flugverkehrskontrolldienste', 3, '§ 4 Abs. 2 Z 1 lit. b'),
    rule('TRANSPORT', 'Schienenverkehr', 'RAIL_PASSENGER', 'Schienenpersonenverkehr', 4, '§ 4 Abs. 2 Z 2 lit. a'),
    rule('TRANSPORT', 'Schienenverkehr', 'RAIL_FREIGHT', 'Schienengueterverkehr', 24, '§ 4 Abs. 2 Z 2 lit. a'),
    rule('TRANSPORT', 'Schienenverkehr', 'RAIL_INFRA', 'Eisenbahninfrastruktur', 4, '§ 4 Abs. 2 Z 2 lit. b'),
    rule('TRANSPORT', 'Schienenverkehr', 'RAIL_CONTROL', 'Zugsteuerung / Signalgebung', 4, '§ 4 Abs. 2 Z 2 lit. b'),
    rule('TRANSPORT', 'Schienenverkehr', 'RAIL_SERVICE', 'Schienenverkehr-Serviceeinrichtungen', 24, '§ 4 Abs. 2 Z 2 lit. c'),
    *(rule('TRANSPORT', 'Schifffahrt', code, label, 24, '§ 4 Abs. 2 Z 3') for code, label in (
        ('SHIPPING', 'Binnen-, See- und Kuestenschifffahrt'), ('PORT', 'Haefen / Hafenanlagen'),
        ('VESSEL_TRAFFIC', 'Schiffsverkehrsdienste'))),
    rule('TRANSPORT', 'Strassenverkehr', 'ROAD_CONTROL', 'Verkehrsmanagementkontrolle', 4, '§ 4 Abs. 2 Z 4'),
    rule('TRANSPORT', 'Strassenverkehr', 'ROAD_ITS', 'Intelligente Verkehrsdienste', 4, '§ 4 Abs. 2 Z 4'),
    rule('TRANSPORT', 'Oeffentlicher Verkehr', 'PUBLIC_TRANSPORT', 'Oeffentlicher Personenverkehr', 4, '§ 4 Abs. 2 Z 5'),
    rule('HEALTH', '', 'REFERENCE_LAB', 'EU-Referenzlaboratorium', 72, '§ 7 Abs. 2 Z 1'),
    rule('HEALTH', '', 'PHARMA_RESEARCH', 'Arzneimittelforschung / -entwicklung', 48, '§ 7 Abs. 2 Z 2'),
    *(rule('HEALTH', '', code, label, 24, '§ 7 Abs. 2 Z 3') for code, label in (
        ('PHARMA_PRODUCTION', 'Pharmazeutische Grundstoffe / Zubereitungen'),
        ('MEDICAL_DEVICES', 'Herstellung kritischer Medizinprodukte'), ('PHARMA_DISTRIBUTION', 'Arzneimittelvertrieb'))),
    rule('HEALTH', '', 'HOSPITAL', 'Krankenanstalten nach § 8 Abs. 1 Z 1 bis 4', 8, '§ 8 Abs. 3 Z 1'),
    rule('HEALTH', '', 'EMERGENCY_DISPATCH', 'Leitstelle Notfallrettungstransporte', 6, '§ 8 Abs. 3 Z 2'),
    rule('WATER', '', 'DRINKING_WATER', 'Trinkwasserversorgung / -lieferung', 600000, '§ 9 Abs. 2', 'USER_HOURS'),
    rule('WASTEWATER', '', 'WASTEWATER', 'Sammlung / Entsorgung / Behandlung von Abwasser', 24, '§ 10 Abs. 2'),
    rule('PUBLIC', '', 'PUBLIC_ADMIN', 'Wesentlicher Dienst der oeffentlichen Verwaltung', 24, '§ 12'),
    rule('SPACE', '', 'SPACE_GROUND', 'Weltraum-Bodeninfrastruktur', 2, '§ 13 Abs. 2'),
    rule('FOOD', '', 'FOOD_PRODUCTION', 'Industrielle Lebensmittelproduktion / -verarbeitung', 72, '§ 14 Abs. 2 Z 1 (drei Tage)'),
    rule('FOOD', '', 'FOOD_LOGISTICS', 'Lebensmittellagerung / -logistik', 24, '§ 14 Abs. 2 Z 2'),
    rule('FOOD', '', 'FOOD_WHOLESALE', 'Lebensmittelgrosshandel', 24, '§ 14 Abs. 2 Z 3'),
)
RULE_BY_CODE = {item.service_code: item for item in RULES}
SERVICE_CHOICES = [(item.service_code, item.label) for item in RULES]
