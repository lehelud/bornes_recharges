"""Onglet « Quelle offre de recharge pour moi ? ».

Croise les bornes Open Data (IRVE) autour de l'adresse de l'utilisateur avec la
base des offres tarifaires (offres_recharge.py) pour recommander l'abonnement
ou le badge le plus rentable.
"""

import numpy as np
import pandas as pd
import requests
import streamlit as st

from offres_recharge import (
    CPO_OFFERS,
    EMSP_OFFERS,
    OPERATOR_LABELS,
    OPERATORS,
    PALIER_LABELS,
)

PRISES = {
    "Combo CCS": "prise_type_combo_ccs",
    "Type 2": "prise_type_2",
    "CHAdeMO": "prise_type_chademo",
    "Prise domestique E/F": "prise_type_ef",
}

GEOCODERS = [
    "https://data.geopf.fr/geocodage/search",      # nouveau point d'accès de la BAN
    "https://api-adresse.data.gouv.fr/search/",    # ancien point d'accès (historique)
]


# ---------------------------------------------------------------------------
# Préparation des données
# ---------------------------------------------------------------------------
def _to_bool(serie):
    return serie.astype(str).str.strip().str.lower().isin(["true", "1", "vrai", "oui"])


def prepare_stations(df):
    """Réduit le fichier IRVE aux colonnes utiles et normalise les opérateurs."""
    cols = [
        "id_station_itinerance", "id_pdc_itinerance", "nom_station", "adresse_station",
        "nom_operateur", "nom_enseigne", "nom_amenageur", "puissance_nominale",
        "condition_acces", "consolidated_longitude", "consolidated_latitude",
    ] + list(PRISES.values())
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

    for col in PRISES.values():
        if col in st_df.columns:
            st_df[col] = _to_bool(st_df[col])

    st_df["palier"] = np.select(
        [st_df["puissance_nominale"] <= 22, st_df["puissance_nominale"] < 150],
        ["AC", "DC"],
        default="HPC",
    )

    # Normalisation opérateur (table operators_mapping)
    texte = (
        st_df["nom_operateur"].fillna("").astype(str) + " | "
        + st_df["nom_enseigne"].fillna("").astype(str) + " | "
        + st_df["nom_amenageur"].fillna("").astype(str)
    ).str.lower()
    prefixe = (
        st_df["id_station_itinerance"].fillna("").astype(str)
        .str.replace(r"[\s\*]", "", regex=True).str[:5].str.upper()
    )
    operator_id = pd.Series("autre", index=st_df.index)
    for op in OPERATORS:
        libre = operator_id == "autre"
        regex = "|".join(op["patterns"])
        match = texte.str.contains(regex, regex=True)
        if op["afirev_prefixes"]:
            match |= prefixe.isin(op["afirev_prefixes"])
        operator_id[libre & match] = op["operator_id"]
    st_df["operator_id"] = operator_id

    return st_df.drop(columns=["consolidated_latitude", "consolidated_longitude",
                               "condition_acces", "nom_amenageur"])


def haversine_km(lat, lon, lats, lons):
    """Distance à vol d'oiseau (km) entre un point et un vecteur de points."""
    r = 6371.0
    lat1, lon1 = np.radians(lat), np.radians(lon)
    lat2, lon2 = np.radians(lats), np.radians(lons)
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def geocode(adresse):
    """Géocode une adresse via la Base Adresse Nationale. Renvoie (label, lat, lon) ou None."""
    for url in GEOCODERS:
        try:
            resp = requests.get(url, params={"q": adresse, "limit": 1}, timeout=8)
            if resp.status_code != 200:
                continue
            features = resp.json().get("features", [])
            if features:
                lon, lat = features[0]["geometry"]["coordinates"]
                return features[0]["properties"].get("label", adresse), float(lat), float(lon)
            return None
        except (requests.RequestException, ValueError, KeyError):
            continue
    return None


# ---------------------------------------------------------------------------
# Moteur de calcul
# ---------------------------------------------------------------------------
def stations_dans_zone(stations, lat, lon, rayon_km, palier, prise):
    # Pré-filtre rapide par boîte englobante, puis distance exacte
    dlat = rayon_km / 111.0
    dlon = rayon_km / (111.0 * max(np.cos(np.radians(lat)), 0.1))
    zone = stations[stations["lat"].between(lat - dlat, lat + dlat)
                    & stations["lon"].between(lon - dlon, lon + dlon)].copy()
    zone["distance_km"] = haversine_km(lat, lon, zone["lat"].values, zone["lon"].values)
    zone = zone[zone["distance_km"] <= rayon_km]
    zone = zone[zone["palier"] == palier]
    if prise in PRISES and PRISES[prise] in zone.columns:
        zone = zone[zone[PRISES[prise]]]
    return zone


def parts_de_marche(zone):
    """Part locale de chaque opérateur (en points de charge) + borne la plus proche."""
    if zone.empty:
        return pd.DataFrame(columns=["operator_id", "nb_pdc", "nb_stations", "part_pct", "plus_proche_km"])
    agg = zone.groupby("operator_id").agg(
        nb_pdc=("id_pdc_itinerance", "count"),
        nb_stations=("id_station_itinerance", "nunique"),
        plus_proche_km=("distance_km", "min"),
    ).reset_index()
    agg["part_pct"] = 100 * agg["nb_pdc"] / agg["nb_pdc"].sum()
    return agg.sort_values("nb_pdc", ascending=False)


def _prix(offer, palier):
    for rule in offer["pricing_rules"]:
        if rule["palier"] == palier:
            return rule["price_per_kwh_eur"]
    return None


def _prix_reference(op_id, palier):
    """Tarif direct sans abonnement de l'opérateur (référence du point mort)."""
    prix = [_prix(o, palier) for o in CPO_OFFERS
            if op_id in o["target_operators"] and o["monthly_fee_eur"] == 0]
    prix = [p for p in prix if p is not None]
    return min(prix) if prix else None


def simuler_offres(parts, palier, energie_mois, nb_sessions):
    """Calcule T_mois = F_abo + E_mois × P_kWh + F_sessions pour chaque offre applicable."""
    lignes = []
    for _, op in parts.iterrows():
        op_id = op["operator_id"]
        if op_id == "autre":
            continue
        p_ref = _prix_reference(op_id, palier)
        candidats = []
        for o in CPO_OFFERS:
            if op_id in o["target_operators"] and _prix(o, palier) is not None:
                candidats.append((o, _prix(o, palier), o["monthly_fee_eur"], "Direct opérateur"))
        if p_ref is not None:
            for o in EMSP_OFFERS:
                prix = o.get("overrides", {}).get(op_id, p_ref * (1 + o["markup_pct"] / 100))
                fixe = o["monthly_fee_eur"] + o["one_time_fee_eur"] / 12
                candidats.append((o, prix, fixe, "Badge multi-réseaux"))

        for o, prix, fixe, type_offre in candidats:
            f_sessions = nb_sessions * o.get("session_fee_eur", 0.0)
            cout = fixe + energie_mois * prix + f_sessions
            seuil = None
            if p_ref is not None and fixe > 0 and prix < p_ref:
                seuil = fixe / (p_ref - prix)
            lignes.append({
                "Offre": o["offer_name"],
                "Émetteur": o["provider_name"],
                "Type": type_offre,
                "Réseau": OPERATOR_LABELS[op_id],
                "Prix (€/kWh)": round(prix, 3),
                "Frais fixes (€/mois)": round(fixe, 2),
                "Coût mensuel (€)": round(cout, 2),
                "Économie vs sans abo (€/mois)": (round(energie_mois * p_ref + f_sessions - cout, 2)
                                                  if p_ref is not None else None),
                "Rentable dès (kWh/mois)": round(seuil, 1) if seuil else None,
                "Points de charge proches": int(op["nb_pdc"]),
                "Borne la plus proche (km)": round(op["plus_proche_km"], 1),
                "Source": o["source_url"],
            })
    res = pd.DataFrame(lignes)
    if res.empty:
        return res
    return res.sort_values(["Coût mensuel (€)", "Frais fixes (€/mois)"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Interface Streamlit
# ---------------------------------------------------------------------------
COULEURS = ["#007ACC", "#1AA6A6", "#E07A1F", "#8E44AD", "#C0392B",
            "#27AE60", "#D4AC0D", "#2C3E50", "#E84393", "#7F8C8D", "#16A085"]


def render(stations):
    st.header("Quelle offre de recharge est la plus adaptée à mon domicile ?")
    st.markdown(
        "Renseignez votre adresse et vos habitudes de conduite : l'application repère les bornes "
        "publiques autour de chez vous (fichier IRVE de data.gouv.fr), identifie leurs opérateurs "
        "et compare les abonnements et badges de recharge pour trouver le moins cher."
    )

    with st.form("form_offres"):
        adresse = st.text_input("Adresse du domicile", placeholder="ex. 20 avenue de Ségur, 75007 Paris")
        c1, c2, c3 = st.columns(3)
        rayon = c1.slider("Rayon de recherche (km)", 1, 30, 5)
        palier = c2.selectbox("Type de recharge publique", ["AC", "DC", "HPC"],
                              index=1, format_func=PALIER_LABELS.get)
        prise = c3.selectbox("Prise du véhicule", list(PRISES.keys()) + ["Indifférent"])

        c4, c5, c6, c7 = st.columns(4)
        km_semaine = c4.number_input("Distance par semaine (km)", 10, 3000, 250, step=10)
        conso = c5.number_input("Consommation (kWh/100 km)", 10.0, 35.0, 17.0, step=0.5)
        batterie = c6.number_input("Capacité batterie (kWh)", 15, 150, 60, step=5)
        part_publique = c7.slider("Part rechargée sur borne publique (%)", 0, 100, 50, step=5,
                                  help="Le reste est supposé rechargé à domicile ou au travail.")
        with st.expander("Je ne connais pas mon adresse exacte / géocodage indisponible"):
            cc1, cc2 = st.columns(2)
            lat_man = cc1.number_input("Latitude", value=0.0, format="%.5f")
            lon_man = cc2.number_input("Longitude", value=0.0, format="%.5f")
        lancer = st.form_submit_button("Trouver la meilleure offre", type="primary")

    if lancer:
        if lat_man != 0.0 and lon_man != 0.0:
            point = (f"Coordonnées {lat_man:.5f}, {lon_man:.5f}", lat_man, lon_man)
        elif adresse.strip():
            with st.spinner("Géocodage de l'adresse (Base Adresse Nationale)…"):
                point = geocode(adresse.strip())
            if point is None:
                st.error("Adresse introuvable ou service de géocodage indisponible. "
                         "Vérifiez l'adresse ou saisissez des coordonnées GPS.")
                return
        else:
            st.warning("Merci de renseigner une adresse.")
            return
        st.session_state["offres_params"] = dict(
            point=point, rayon=rayon, palier=palier, prise=prise, km_semaine=km_semaine,
            conso=conso, batterie=batterie, part_publique=part_publique,
        )

    params = st.session_state.get("offres_params")
    if not params:
        return
    _afficher_resultats(stations, **params)


def _afficher_resultats(stations, point, rayon, palier, prise, km_semaine, conso, batterie, part_publique):
    label, lat, lon = point
    energie_mois = km_semaine * 52 / 12 * conso / 100 * part_publique / 100
    kwh_par_session = 0.7 * batterie  # recharge typique de 10 % à 80 %
    nb_sessions = energie_mois / kwh_par_session if kwh_par_session else 0

    st.success(f"📍 {label}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Énergie publique estimée", f"{energie_mois:.0f} kWh/mois")
    m2.metric("Recharges publiques", f"≈ {nb_sessions:.1f} / mois",
              help="Une recharge = 10 % → 80 % de la batterie.")
    zone = stations_dans_zone(stations, lat, lon, rayon, palier, prise)
    m3.metric(f"Points de charge à moins de {rayon} km", f"{len(zone):,}".replace(",", " "))

    if zone.empty:
        st.warning("Aucune borne publique compatible dans ce rayon. Essayez d'élargir le rayon "
                   "ou de changer le type de recharge.")
        return

    parts = parts_de_marche(zone)
    resultats = simuler_offres(parts, palier, energie_mois, nb_sessions)

    # --- Recommandation principale
    if resultats.empty:
        st.info("Les opérateurs présents autour de vous n'ont pas de tarif référencé dans notre base.")
    else:
        best = resultats.iloc[0]
        st.subheader("🏆 Offre recommandée")
        st.markdown(
            f"**{best['Offre']}** ({best['Émetteur']}) sur le réseau **{best['Réseau']}** : "
            f"environ **{best['Coût mensuel (€)']:.2f} € / mois** "
            f"({best['Prix (€/kWh)']:.3f} €/kWh, {best['Frais fixes (€/mois)']:.2f} € de frais fixes). "
            f"Borne la plus proche à {best['Borne la plus proche (km)']} km "
            f"({best['Points de charge proches']} points de charge dans la zone)."
        )
        if pd.notna(best["Rentable dès (kWh/mois)"]):
            st.caption(
                f"Cet abonnement devient rentable dès {best['Rentable dès (kWh/mois)']:.0f} kWh rechargés "
                f"par mois — vous en rechargez environ {energie_mois:.0f}. "
                "C'est comme une carte d'abonnement au cinéma : elle n'est intéressante que si "
                "vous y allez assez souvent pour que la réduction par séance rembourse la carte."
            )

        st.subheader("Comparatif de toutes les offres applicables")
        st.dataframe(
            resultats,
            hide_index=True,
            
            column_config={"Source": st.column_config.LinkColumn("Source", display_text="Grille tarifaire")},
        )
        st.caption(
            "Simulation : coût mensuel = abonnement + énergie × prix au kWh + frais de session, "
            "en supposant que toute votre recharge publique se fait sur le réseau indiqué. "
            "Les badges payants à l'achat sont amortis sur 12 mois. Tarifs indicatifs, à vérifier "
            "sur la grille de l'opérateur (frais d'occupation non inclus)."
        )

    # --- Opérateurs présents
    st.subheader("Opérateurs présents autour de chez vous")
    parts_aff = parts.assign(Opérateur=parts["operator_id"].map(OPERATOR_LABELS))
    part_autre = parts.loc[parts["operator_id"] == "autre", "part_pct"].sum()
    g1, g2 = st.columns([1, 1])
    g1.bar_chart(parts_aff.set_index("Opérateur")["part_pct"], horizontal=True,
                 x_label="Part des points de charge (%)", y_label="")
    g2.dataframe(
        parts_aff[["Opérateur", "nb_stations", "nb_pdc", "part_pct", "plus_proche_km"]].rename(columns={
            "nb_stations": "Stations", "nb_pdc": "Points de charge",
            "part_pct": "Part (%)", "plus_proche_km": "Plus proche (km)"}).round(1),
        hide_index=True,
    )
    if part_autre > 0:
        st.caption(
            f"{part_autre:.0f} % des points de charge de la zone appartiennent à des opérateurs "
            "(souvent des réseaux de collectivités) dont le tarif n'est pas référencé : ils restent "
            "généralement accessibles avec un badge multi-réseaux (Chargemap, Electroverse…)."
        )

    # --- Carte
    st.subheader("Carte des bornes compatibles")
    ops = list(parts["operator_id"])
    couleur_op = {op: COULEURS[i % len(COULEURS)] for i, op in enumerate(ops)}
    carte = zone[["lat", "lon", "operator_id"]].copy()
    carte["color"] = carte["operator_id"].map(couleur_op)
    carte["size"] = 40
    domicile = pd.DataFrame({"lat": [lat], "lon": [lon], "operator_id": ["domicile"],
                             "color": ["#000000"], "size": [150]})
    st.map(pd.concat([carte, domicile]), latitude="lat", longitude="lon", color="color", size="size")
    st.markdown(
        " ".join(f"<span style='color:{couleur_op[op]}'>●</span> {OPERATOR_LABELS[op]}" for op in ops)
        + " <span>⬤</span> Domicile",
        unsafe_allow_html=True,
    )
