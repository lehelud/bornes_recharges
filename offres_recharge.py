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
    {"operator_id": "leclerc", "label": "E.Leclerc (Charge E-Lec)", "afirev_prefixes": ["FRLE2"], "patterns": [r"leclerc", r"charge e-lec"]},
    {"operator_id": "atlante", "label": "Atlante", "afirev_prefixes": ["FRATL"], "patterns": [r"\batlante\b"]},
    {"operator_id": "powerdot", "label": "Powerdot", "afirev_prefixes": ["FRPD1"], "patterns": [r"power ?dot"]},
    {"operator_id": "driveco", "label": "Driveco", "afirev_prefixes": [], "patterns": [r"driveco"]},
    {"operator_id": "eborn", "label": "Réseau eborn", "afirev_prefixes": ["FREBN"], "patterns": [r"\be-?born\b", r"spbr1"]},
    {"operator_id": "metropolis", "label": "Métropolis (Grand Paris)", "afirev_prefixes": ["FRMGP"], "patterns": [r"m[ée]tropolis"]},
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
# Réseaux locaux / régionaux ajoutés (tarifs relevés en novembre 2026).
# `fiabilite` : "officiel" (grille publiée), "indicatif" (presse / comparateurs),
# "estimation" (prix affiché borne par borne : valeur moyenne estimée).
# `operator_rules` : tarifs spécifiques à un autre réseau couvert par l'offre.
# ---------------------------------------------------------------------------
LOCAL_OFFERS = [
    # E.LECLERC : 0,17 €/kWh en AC depuis le 05/10/2026 ; DC affiché borne par borne
    {"offer_id": "leclerc_direct", "provider_name": "E.Leclerc", "offer_name": "Charge E-Lec (sans abonnement)",
     "target_operators": ["leclerc"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.17),
     "fiabilite": "indicatif",
     "source_url": "https://www.automobile-propre.com/articles/recharge-des-voitures-electriques-leclerc-baisse-encore-son-prix-pour-etre-moins-cher-que-lidl/"},
    # ATLANTE : ~0,54 €/kWh sans abonnement ; Atlante Go 9,99 €/mois → 0,29 €/kWh (+ Powerdot à 0,39)
    {"offer_id": "atlante_direct", "provider_name": "Atlante", "offer_name": "Atlante sans abonnement",
     "target_operators": ["atlante"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.54, dc=0.54, hpc=0.54),
     "fiabilite": "indicatif",
     "source_url": "https://electroverse.com/fr-FR/community/ev-blogs-and-guides/combien-co-te-la-recharge-d-une-voiture-lectrique-en-france"},
    {"offer_id": "atlante_go", "provider_name": "Atlante", "offer_name": "Atlante Go",
     "target_operators": ["atlante", "powerdot"], "monthly_fee_eur": 9.99,
     "pricing_rules": _rules(ac=0.29, dc=0.29, hpc=0.29),
     "operator_rules": {"powerdot": _rules(ac=0.39, dc=0.39, hpc=0.39)},
     "fiabilite": "indicatif",
     "source_url": "https://www.automobile-propre.com/breves/atlante-go-un-nouveau-forfait-avec-un-tarif-unique-ideal-pour-les-clients-reguliers/"},
    # POWERDOT : prix sans abonnement affiché sur la borne (fourchette 0,30-0,53 €/kWh)
    {"offer_id": "powerdot_direct", "provider_name": "Powerdot", "offer_name": "Powerdot sans abonnement",
     "target_operators": ["powerdot"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.40, dc=0.55, hpc=0.55),
     "fiabilite": "estimation",
     "source_url": "https://electroverse.com/fr/community/ev-blogs-and-guides/le-guide-ultime-du-reseau-de-recharge-:-powerdot"},
    {"offer_id": "powerdot_199", "provider_name": "Powerdot", "offer_name": "Powerdot abonnement 1,99 €",
     "target_operators": ["powerdot"], "monthly_fee_eur": 1.99, "pricing_rules": _rules(ac=0.36, dc=0.52, hpc=0.52),
     "fiabilite": "indicatif", "source_url": "https://lesvoitures.fr/prix-recharge-voiture-electrique/"},
    {"offer_id": "powerdot_499", "provider_name": "Powerdot", "offer_name": "Powerdot abonnement 4,99 €",
     "target_operators": ["powerdot"], "monthly_fee_eur": 4.99, "pricing_rules": _rules(ac=0.29, dc=0.41, hpc=0.41),
     "fiabilite": "indicatif", "source_url": "https://lesvoitures.fr/prix-recharge-voiture-electrique/"},
    # DRIVECO : prix par station (relevés 0,62-0,70 €/kWh en DC)
    {"offer_id": "driveco_direct", "provider_name": "Driveco", "offer_name": "Driveco paiement direct",
     "target_operators": ["driveco"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(dc=0.65, hpc=0.63),
     "fiabilite": "estimation", "source_url": "https://seety.co/fr/recharge-electrique-pas-cher"},
    # EBORN (réseau des syndicats d'énergie du Sud-Est) : abonnement 10 €/an
    {"offer_id": "eborn_direct", "provider_name": "eborn", "offer_name": "eborn sans abonnement",
     "target_operators": ["eborn"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.34, dc=0.44),
     "fiabilite": "indicatif", "source_url": "https://web.uta.com/hubfs/UTA_eCharge_Tariffs_FR_2603.pdf"},
    {"offer_id": "eborn_abo", "provider_name": "eborn", "offer_name": "eborn abonné (10 €/an)",
     "target_operators": ["eborn"], "monthly_fee_eur": round(10 / 12, 2), "pricing_rules": _rules(ac=0.24, dc=0.34),
     "fiabilite": "indicatif", "source_url": "https://www.automobile-propre.com/articles/le-reseau-e-born-facture-la-charge-au-kwh/"},
    # METROPOLIS (Grand Paris hors Paris) : grille sans abonnement
    {"offer_id": "metropolis_direct", "provider_name": "Métropolis", "offer_name": "Métropolis sans abonnement",
     "target_operators": ["metropolis"], "monthly_fee_eur": 0.0, "pricing_rules": _rules(ac=0.45, dc=0.60, hpc=0.65),
     "fiabilite": "indicatif", "source_url": "https://metropolegrandparis.fr/sites/default/files/media/document/Plaquette%20M%C3%A9tropolis.pdf"},
]

for _o in CPO_OFFERS:
    _o.setdefault("fiabilite", "officiel")
CPO_OFFERS = CPO_OFFERS + LOCAL_OFFERS

# Prix moyen de marché utilisé quand aucun réseau référencé n'est disponible
PRIX_MARCHE = {"AC": 0.40, "DC": 0.55, "HPC": 0.59}

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
for _o in EMSP_OFFERS:
    _o.setdefault("fiabilite", "indicatif")

LAST_VERIFIED = "Grille issue du document fourni par l'utilisateur (tarifs publics indicatifs)"
