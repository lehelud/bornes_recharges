"""Moteur de calcul : normalisation des bornes et simulation des offres.

Principe (cf. spécifications §4) :
    T_mois = F_abo + Σ_palier (E_palier × P_kWh) + F_sessions

En mode « mixte », l'utilisateur répartit son énergie entre plusieurs types de
recharge (AC, DC, ultra-rapide). Pour chaque combinaison d'abonnements (aucun,
un seul, ou deux), on affecte chaque palier au tarif le moins cher accessible
dans la zone, en tenant compte des abonnements souscrits.
"""

from itertools import combinations

import numpy as np
import pandas as pd

from offres_recharge import (
    CPO_OFFERS,
    EMSP_OFFERS,
    OPERATOR_LABELS,
    OPERATORS,
    PALIER_LABELS,
    PRIX_MARCHE,
)

COLS_PRISES = ["prise_type_ef", "prise_type_2", "prise_type_combo_ccs", "prise_type_chademo"]
PRISES_RAPIDES = {"Combo CCS": "prise_type_combo_ccs", "CHAdeMO": "prise_type_chademo"}
PALIERS = ["AC", "DC", "HPC"]
EMSP_IDS = {o["offer_id"] for o in EMSP_OFFERS}


# ---------------------------------------------------------------------------
# Préparation des données Open Data
# ---------------------------------------------------------------------------
def _to_bool(serie):
    return serie.astype(str).str.strip().str.lower().isin(["true", "1", "vrai", "oui"])


def prepare_stations(df):
    """Réduit le fichier IRVE aux colonnes utiles et normalise les opérateurs."""
    cols = [
        "id_station_itinerance", "id_pdc_itinerance", "nom_station", "adresse_station",
        "nom_operateur", "nom_enseigne", "nom_amenageur", "puissance_nominale",
        "condition_acces", "consolidated_longitude", "consolidated_latitude",
    ] + COLS_PRISES
    st_df = df[[c for c in cols if c in df.columns]].copy()

    st_df["lat"] = pd.to_numeric(st_df["consolidated_latitude"], errors="coerce")
    st_df["lon"] = pd.to_numeric(st_df["consolidated_longitude"], errors="coerce")
    st_df["puissance_nominale"] = pd.to_numeric(st_df["puissance_nominale"], errors="coerce")
    # Quelques producteurs déclarent la puissance en W au lieu de kW
    st_df.loc[st_df["puissance_nominale"] > 1000, "puissance_nominale"] /= 1000
    st_df = st_df.dropna(subset=["lat", "lon", "puissance_nominale"])
    st_df = st_df[st_df["puissance_nominale"] > 0]
    # Uniquement les bornes ouvertes au public
    st_df = st_df[st_df["condition_acces"].astype(str).str.strip().str.lower() == "accès libre"]

    for col in COLS_PRISES:
        if col in st_df.columns:
            st_df[col] = _to_bool(st_df[col])

    st_df["palier"] = np.select(
        [st_df["puissance_nominale"] <= 22, st_df["puissance_nominale"] < 150],
        ["AC", "DC"], default="HPC",
    )

    # Normalisation opérateur (table operators_mapping)
    texte = (
        st_df["nom_operateur"].fillna("").astype(str) + " | "
        + st_df["nom_enseigne"].fillna("").astype(str) + " | "
        + st_df["nom_amenageur"].fillna("").astype(str)
    ).str.lower()
    prefixe = (st_df["id_station_itinerance"].fillna("").astype(str)
               .str.replace(r"[\s\*]", "", regex=True).str[:5].str.upper())
    operator_id = pd.Series("autre", index=st_df.index)
    for op in OPERATORS:
        libre = operator_id == "autre"
        match = texte.str.contains("|".join(op["patterns"]), regex=True)
        if op["afirev_prefixes"]:
            match |= prefixe.isin(op["afirev_prefixes"])
        operator_id[libre & match] = op["operator_id"]
    st_df["operator_id"] = operator_id

    return st_df.drop(columns=["consolidated_latitude", "consolidated_longitude",
                               "condition_acces", "nom_amenageur"])


def filtrer_compatibles(zone, prise_rapide):
    """AC : prise Type 2 ou domestique. DC / ultra-rapide : prise rapide du véhicule."""
    ac = (zone["palier"] == "AC") & (zone["prise_type_2"] | zone["prise_type_ef"])
    col = PRISES_RAPIDES.get(prise_rapide)
    rapide = (zone["palier"] != "AC") & (zone[col] if col else False)
    return zone[ac | rapide]


def restreindre_ac_aux_lieux(zone, lieux=("Domicile", "Travail")):
    """Une recharge lente (AC) dure plusieurs heures : on ne la fait pas en cours de trajet.
    Les bornes AC ne sont donc retenues qu'autour du domicile et du lieu de travail."""
    pres_lieu = zone["zones"].str.contains("|".join(lieux))
    return zone[(zone["palier"] != "AC") | pres_lieu]


def parts_de_marche(zone):
    """Par opérateur et palier : points de charge, stations, borne la plus proche."""
    if zone.empty:
        return pd.DataFrame(columns=["operator_id", "palier", "nb_pdc", "nb_stations",
                                     "plus_proche_km", "zone_proche"])
    grp = zone.groupby(["operator_id", "palier"])
    res = grp.agg(
        nb_pdc=("id_pdc_itinerance", "count"),
        nb_stations=("id_station_itinerance", "nunique"),
        plus_proche_km=("distance_km", "min"),
    )
    res["zone_proche"] = zone.loc[grp["distance_km"].idxmin(), "zones"].values
    return res.reset_index()


# ---------------------------------------------------------------------------
# Tarifs
# ---------------------------------------------------------------------------
def _prix_cpo(offer, op_id, palier):
    if op_id not in offer["target_operators"]:
        return None
    rules = offer.get("operator_rules", {}).get(op_id, offer["pricing_rules"])
    for rule in rules:
        if rule["palier"] == palier:
            return rule["price_per_kwh_eur"]
    return None


def prix_reference(op_id, palier):
    """Tarif direct sans abonnement de l'opérateur (référence du point mort)."""
    prix = [_prix_cpo(o, op_id, palier) for o in CPO_OFFERS if o["monthly_fee_eur"] == 0]
    prix = [p for p in prix if p is not None]
    return min(prix) if prix else None


def prix_offre(offer, op_id, palier):
    """Prix au kWh d'une offre (CPO ou eMSP) sur un réseau et un palier donnés."""
    if offer["offer_id"] in EMSP_IDS:
        p_ref = prix_reference(op_id, palier)
        if p_ref is None:
            return None
        return offer.get("overrides", {}).get(op_id, p_ref * (1 + offer["markup_pct"] / 100))
    return _prix_cpo(offer, op_id, palier)


def frais_fixes(offer):
    """Coût fixe mensuel : abonnement + achat du badge amorti sur 12 mois."""
    return offer["monthly_fee_eur"] + offer.get("one_time_fee_eur", 0.0) / 12


def _type(offer):
    return "Badge multi-réseaux" if offer["offer_id"] in EMSP_IDS else "Direct opérateur"


# ---------------------------------------------------------------------------
# Simulation « une offre = un réseau » (détail par palier)
# ---------------------------------------------------------------------------
def simuler_offres(parts, palier, energie_mois, nb_sessions):
    """Coût mensuel de chaque offre si toute l'énergie du palier est prise sur un réseau."""
    lignes = []
    for _, op in parts[parts["palier"] == palier].iterrows():
        op_id = op["operator_id"]
        if op_id == "autre":
            continue
        p_ref = prix_reference(op_id, palier)
        for o in CPO_OFFERS + EMSP_OFFERS:
            prix = prix_offre(o, op_id, palier)
            if prix is None:
                continue
            fixe = frais_fixes(o)
            f_sessions = nb_sessions * o.get("session_fee_eur", 0.0)
            cout = fixe + energie_mois * prix + f_sessions
            seuil = fixe / (p_ref - prix) if (p_ref is not None and fixe > 0 and prix < p_ref) else None
            lignes.append({
                "Offre": o["offer_name"], "Émetteur": o["provider_name"], "Type": _type(o),
                "Réseau": OPERATOR_LABELS[op_id],
                "Prix (€/kWh)": round(prix, 3), "Frais fixes (€/mois)": round(fixe, 2),
                "Coût mensuel (€)": round(cout, 2),
                "Rentable dès (kWh/mois)": round(seuil, 1) if seuil else None,
                "Points de charge": int(op["nb_pdc"]),
                "Plus proche (km)": round(op["plus_proche_km"], 1),
                "Fiabilité du tarif": o["fiabilite"], "Source": o["source_url"],
            })
    res = pd.DataFrame(lignes)
    if res.empty:
        return res
    return res.sort_values(["Coût mensuel (€)", "Frais fixes (€/mois)"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Simulation « panier » : combinaisons d'abonnements sur plusieurs paliers
# ---------------------------------------------------------------------------
def _options(parts):
    """Liste des (offre, réseau, palier, prix) accessibles dans la zone."""
    opts = []
    for _, op in parts.iterrows():
        if op["operator_id"] == "autre":
            continue
        for o in CPO_OFFERS + EMSP_OFFERS:
            prix = prix_offre(o, op["operator_id"], op["palier"])
            if prix is not None:
                opts.append({"offer": o, "op": op["operator_id"], "palier": op["palier"], "prix": prix,
                             "plus_proche_km": op["plus_proche_km"], "zone": op["zone_proche"]})
    return opts


def _evaluer(abonnements, opts, energies):
    """Coût d'un panier : abonnements souscrits + chaque palier au meilleur prix accessible."""
    ids = {o["offer_id"] for o in abonnements}
    fixe = sum(frais_fixes(o) for o in abonnements)
    cout_energie, detail, utilises, non_reference = 0.0, [], set(), []
    for palier, e in energies.items():
        if e <= 0:
            continue
        accessibles = [x for x in opts if x["palier"] == palier
                       and (frais_fixes(x["offer"]) == 0 or x["offer"]["offer_id"] in ids)]
        if accessibles:
            best = min(accessibles, key=lambda x: (x["prix"], frais_fixes(x["offer"]), x["plus_proche_km"]))
            utilises.add(best["offer"]["offer_id"])
            prix, label = best["prix"], (f"{OPERATOR_LABELS[best['op']]} via « {best['offer']['offer_name']} »"
                                         f" (à {best['plus_proche_km']:.1f} km — {best['zone']})"
                                         + (" ⚠️ tarif estimé" if best["offer"]["fiabilite"] == "estimation" else ""))
        else:
            prix, label = PRIX_MARCHE[palier], "aucun réseau référencé : prix moyen du marché"
            non_reference.append(palier)
        cout_energie += e * prix
        detail.append(f"{PALIER_LABELS[palier]} — {e:.0f} kWh à {prix:.3f} €/kWh : {label}")
    return {"fixe": fixe, "energie": cout_energie, "total": fixe + cout_energie,
            "detail": detail, "inutile": bool(ids - utilises), "non_reference": non_reference}


def simuler_paniers(parts, energies, max_abonnements=2, top=5):
    """Classe les combinaisons de 0, 1 ou 2 abonnements payants par coût mensuel."""
    opts = _options(parts)
    paliers_actifs = {p for p, e in energies.items() if e > 0}
    payants = {x["offer"]["offer_id"]: x["offer"] for x in opts
               if frais_fixes(x["offer"]) > 0 and x["palier"] in paliers_actifs}
    payants = list(payants.values())

    base = _evaluer([], opts, energies)
    e_total = sum(energies.values())
    scenarios = [([], base)]
    for k in range(1, max_abonnements + 1):
        for combo in combinations(payants, k):
            res = _evaluer(list(combo), opts, energies)
            if not res["inutile"]:      # un abonnement qui ne sert à aucun palier est écarté
                scenarios.append((list(combo), res))

    lignes = []
    for combo, res in scenarios:
        gain_energie = base["energie"] - res["energie"]
        seuil = None
        if combo and gain_energie > 0 and e_total > 0:
            seuil = res["fixe"] / (gain_energie / e_total)   # point mort en kWh/mois
        lignes.append({
            "Abonnement(s)": " + ".join(o["offer_name"] for o in combo) or "Aucun abonnement",
            "Coût mensuel (€)": round(res["total"], 2),
            "dont frais fixes (€)": round(res["fixe"], 2),
            "Économie vs sans abonnement (€/mois)": round(base["total"] - res["total"], 2),
            "Rentable dès (kWh/mois)": round(seuil, 0) if seuil else None,
            "Où recharger": res["detail"],
            "non_reference": res["non_reference"],
            "nb": len(combo),
        })
    res = pd.DataFrame(lignes).sort_values(["Coût mensuel (€)", "nb"]).reset_index(drop=True)
    return res.head(top), base
