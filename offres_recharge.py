"""Base de données des offres de recharge (CPO & eMSP) en France.

Transcription du document « Comparatif des Offres des Opérateurs de Recharge
(CPO & eMSP) - France ». Les tarifs sont indicatifs : quand la source donne une
fourchette (Tesla, Izivia Fast, IECharge), on retient le milieu de la fourchette.

Structure (cf. spécifications techniques, §3) :
- OPERATORS : table `operators_mapping` (normalisation des noms Open Data).
- OFFERS    : table `tariffs_and_subscriptions` (offres commerciales).
"""

# Paliers de puissance utilisés par le moteur de calcul
PALIERS = {
    "AC": (0, 22),            # Recharge lente / accélérée (≤ 22 kW)
    "DC": (22.01, 149.99),    # Recharge rapide (50 à 150 kW)
    "HPC": (150, 10_000),     # Ultra-rapide (≥ 150 kW)
}

PALIER_LABELS = {
    "AC": "Lente / accélérée (AC ≤ 22 kW)",
    "DC": "Rapide (DC 50 – 150 kW)",
    "HPC": "Ultra-rapide (≥ 150 kW)",
}

# ---------------------------------------------------------------------------
# Table operators_mapping
# L'ordre compte : le premier motif trouvé gagne (Lidl avant TotalEnergies car
# certaines bornes Lidl sont exploitées par Freshmile, etc.).
# `patterns` : expressions régulières (insensibles à la casse) cherchées dans
# nom_operateur, nom_enseigne et nom_amenageur.
# `afirev_prefixes` : préfixes de id_station_itinerance (sans « * »).
# ---------------------------------------------------------------------------
OPERATORS = [
    {"operator_id": "lidl", "label": "Lidl", "afirev_prefixes": [], "patterns": [r"\blidl\b"]},
    {"operator_id": "ionity", "label": "Ionity", "afirev_prefixes": ["FRION"], "patterns": [r"ionity"]},
    {"operator_id": "tesla", "label": "Tesla Superchargeurs", "afirev_prefixes": ["FRTSL"], "patterns": [r"\btesla\b"]},
    {"operator_id": "electra", "label": "Electra", "afirev_prefixes": ["FRELC"], "patterns": [r"\belectra\b"]},
    {"operator_id": "fastned", "label": "Fastned", "afirev_prefixes": ["FRFAS"], "patterns": [r"fastned"]},
    {"operator_id": "iecharge", "label": "IECharge", "afirev_prefixes": ["FRIEN"], "patterns": [r"iecharge"]},
    {"operator_id": "allego", "label": "Allego", "afirev_prefixes": ["FRALL"], "patterns": [r"\ballego\b"]},
    {"operator_id": "engie", "label": "ENGIE Vianeo", "afirev_prefixes": ["FRLMS"], "patterns": [r"vianeo", r"engie mobilit"]},
    {"operator_id": "izivia", "label": "Izivia (EDF)", "afirev_prefixes": [], "patterns": [r"izivia"]},
    {"operator_id": "totalenergies", "label": "TotalEnergies", "afirev_prefixes": [], "patterns": [r"totalenergies", r"total marketing"]},
]

OPERATOR_LABELS = {o["operator_id"]: o["label"] for o in OPERATORS}
OPERATOR_LABELS["autre"] = "Autre opérateur (tarif non référencé)"


def _r(palier, prix):
    """Raccourci : règle tarifaire pour un palier de puissance."""
    pmin, pmax = PALIERS[palier]
    return {"palier": palier, "power_min_kw": pmin, "power_max_kw": pmax, "price_per_kwh_eur": prix}


def _rules(ac=None, dc=None, hpc=None):
    rules = []
    for palier, prix in (("AC", ac), ("DC", dc), ("HPC", hpc)):
        if prix is not None:
            rules.append(_r(palier, prix))
    return rules


# ---------------------------------------------------------------------------
# Table tariffs_and_subscriptions — offres directes des opérateurs (CPO)
# ---------------------------------------------------------------------------
CPO_OFFERS = [
    # IONITY (ultra-rapide uniquement)
    {"offer_id": "ionity_direct", "provider_name": "Ionity", "offer_name": "Ionity Direct (sans abonnement)",
     "target_operators": ["ionity"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(dc=0.59, hpc=0.59),
     "source_url": "https://www.ionity.eu/fr/ionity/tarifs"},
    {"offer_id": "ionity_motion", "provider_name": "Ionity", "offer_name": "Ionity Passport Motion",
     "target_operators": ["ionity"], "monthly_fee_eur": 5.99, "pricing_rules": _rules(dc=0.39, hpc=0.39),
     "source_url": "https://www.ionity.eu/fr/ionity/tarifs"},
    {"offer_id": "ionity_power", "provider_name": "Ionity", "offer_name": "Ionity Passport Power",
     "target_operators": ["ionity"], "monthly_fee_eur": 11.99, "pricing_rules": _rules(dc=0.33, hpc=0.33),
     "source_url": "https://www.ionity.eu/fr/ionity/tarifs"},
    # TESLA (fourchettes : 0,39-0,52 sans abo ; 0,28-0,38 avec abo)
    {"offer_id": "tesla_sans_abo", "provider_name": "Tesla", "offer_name": "Superchargeur sans abonnement (non-Tesla)",
     "target_operators": ["tesla"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(dc=0.455, hpc=0.455),
     "source_url": "https://www.tesla.com/fr_fr/support/supercharging-other-evs"},
    {"offer_id": "tesla_abo", "provider_name": "Tesla", "offer_name": "Superchargeur avec abonnement",
     "target_operators": ["tesla"], "monthly_fee_eur": 9.99, "pricing_rules": _rules(dc=0.33, hpc=0.33),
     "source_url": "https://www.tesla.com/fr_fr/support/supercharging-other-evs"},
    # ELECTRA
    {"offer_id": "electra_std", "provider_name": "Electra", "offer_name": "Electra Standard (app ou CB)",
     "target_operators": ["electra"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.29, dc=0.49, hpc=0.49),
     "source_url": "https://www.go-electra.com/fr/pricing/"},
    {"offer_id": "electra_boost", "provider_name": "Electra", "offer_name": "Electra+ Boost",
     "target_operators": ["electra"], "monthly_fee_eur": 4.99, "pricing_rules": _rules(ac=0.29, dc=0.39, hpc=0.39),
     "source_url": "https://www.go-electra.com/fr/pricing/"},
    {"offer_id": "electra_max", "provider_name": "Electra", "offer_name": "Electra+ Max",
     "target_operators": ["electra"], "monthly_fee_eur": 19.99, "pricing_rules": _rules(ac=0.29, dc=0.29, hpc=0.29),
     "source_url": "https://www.go-electra.com/fr/pricing/"},
    # FASTNED
    {"offer_id": "fastned_std", "provider_name": "Fastned", "offer_name": "Fastned Standard (sans abonnement)",
     "target_operators": ["fastned"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(dc=0.59, hpc=0.59),
     "source_url": "https://www.fastnedcharging.com/fr/tarifs"},
    {"offer_id": "fastned_gold", "provider_name": "Fastned", "offer_name": "Fastned Gold Member",
     "target_operators": ["fastned"], "monthly_fee_eur": 11.99, "pricing_rules": _rules(dc=0.41, hpc=0.41),
     "source_url": "https://www.fastnedcharging.com/fr/tarifs"},
    # TOTALENERGIES
    {"offer_id": "total_direct", "provider_name": "TotalEnergies", "offer_name": "TotalEnergies paiement direct / Charge+",
     "target_operators": ["totalenergies"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.35, dc=0.49, hpc=0.59),
     "source_url": "https://services.totalenergies.fr/particuliers/mobilite-electrique/tarifs-recharge"},
    # ENGIE VIANEO
    {"offer_id": "engie_direct", "provider_name": "ENGIE Vianeo", "offer_name": "ENGIE Vianeo paiement direct",
     "target_operators": ["engie"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.35, dc=0.49, hpc=0.57),
     "source_url": "https://www.engie-vianeo.com/nos-tarifs/"},
    # ALLEGO
    {"offer_id": "allego_direct", "provider_name": "Allego", "offer_name": "Allego tarif direct",
     "target_operators": ["allego"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.49, dc=0.59, hpc=0.69),
     "source_url": "https://www.allego.eu/fr-fr/consommateurs/tarifs"},
    # LIDL
    {"offer_id": "lidl_direct", "provider_name": "Lidl", "offer_name": "Lidl (Lidl Plus ou CB)",
     "target_operators": ["lidl"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.29, dc=0.39, hpc=0.39),
     "source_url": "https://www.lidl.fr/c/stations-de-recharge-electrique/s10007751"},
    # IZIVIA : seul le tarif Izivia Fast (≥ 150 kW, McDonald's) est public et national
    {"offer_id": "izivia_fast", "provider_name": "Izivia", "offer_name": "Izivia Fast (CB ou Pass Izivia)",
     "target_operators": ["izivia"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(hpc=0.325),
     "source_url": "https://www.izivia.com/offres-particuliers/pass-izivia"},
    # IECHARGE (fourchette 0,25-0,30)
    {"offer_id": "iecharge_direct", "provider_name": "IECharge", "offer_name": "IECharge tarif unique",
     "target_operators": ["iecharge"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(dc=0.275, hpc=0.275),
     "source_url": "https://iecharge.io/fr/"},
]

# ---------------------------------------------------------------------------
# Offres eMSP (badges multi-réseaux)
# `markup_pct` : commission appliquée sur le tarif direct de l'opérateur.
# `one_time_fee_eur` : achat du badge, amorti sur 12 mois dans la simulation.
# `overrides` : tarifs négociés spécifiques à un opérateur.
# ---------------------------------------------------------------------------
EMSP_OFFERS = [
    {"offer_id": "electroverse", "provider_name": "Octopus Electroverse", "offer_name": "Electroverse (carte gratuite)",
     "target_operators": ["ALL"], "monthly_fee_eur": 0.0, "one_time_fee_eur": 0.0, "markup_pct": 0.0,
     "source_url": "https://electroverse.octopus.energy/fr"},
    {"offer_id": "chargemap", "provider_name": "Chargemap", "offer_name": "Chargemap Pass",
     "target_operators": ["ALL"], "monthly_fee_eur": 0.0, "one_time_fee_eur": 19.90, "markup_pct": 12.5,
     "source_url": "https://fr.chargemap.com/pass"},
    {"offer_id": "mobilize_basic", "provider_name": "Mobilize (Renault)", "offer_name": "Mobilize Charge Pass Basic",
     "target_operators": ["ALL"], "monthly_fee_eur": 0.0, "one_time_fee_eur": 0.0, "markup_pct": 10.0,
     "source_url": "https://www.mobilize.fr/offres/mobilize-charge-pass.html"},
    {"offer_id": "mobilize_intense", "provider_name": "Mobilize (Renault)", "offer_name": "Mobilize Charge Pass Intense",
     "target_operators": ["ALL"], "monthly_fee_eur": 4.99, "one_time_fee_eur": 0.0, "markup_pct": 10.0,
     "overrides": {"ionity": 0.29},
     "source_url": "https://www.mobilize.fr/offres/mobilize-charge-pass.html"},
    {"offer_id": "izivia_pass", "provider_name": "Izivia", "offer_name": "Pass Izivia sans abonnement",
     "target_operators": ["ALL"], "monthly_fee_eur": 0.0, "one_time_fee_eur": 15.0, "markup_pct": 10.0,
     "source_url": "https://www.izivia.com/offres-particuliers/pass-izivia"},
]

LAST_VERIFIED = "Grille issue du document fourni par l'utilisateur (tarifs publics indicatifs)"
