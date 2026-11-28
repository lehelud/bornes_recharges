"""Onglet « Quelle offre de recharge pour moi ? » (interface Streamlit).

Croise les bornes Open Data (IRVE) autour du domicile, du lieu de travail et des
trajets récurrents avec la base des offres tarifaires (offres_recharge.py).
"""

import pandas as pd
import pydeck as pdk
import streamlit as st

import geo
import moteur
from moteur import prepare_stations  # noqa: F401  (utilisé par app.py)
from offres_recharge import OPERATOR_LABELS, PALIER_LABELS

COULEURS = ["#007ACC", "#1AA6A6", "#E07A1F", "#8E44AD", "#C0392B", "#27AE60", "#D4AC0D",
            "#2C3E50", "#E84393", "#7F8C8D", "#16A085", "#A04000", "#5DADE2", "#58D68D",
            "#F5B041", "#AF7AC5", "#000080"]


def _hex_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _localiser(nom, adresse):
    """Géocode une adresse facultative. Renvoie (label, lat, lon), None si vide, ou False si introuvable."""
    if not adresse.strip():
        return None
    point = geo.geocode(adresse.strip())
    if point is None:
        st.error(f"{nom} : adresse introuvable ou service de géocodage indisponible.")
        return False
    return point


# ---------------------------------------------------------------------------
# Formulaire
# ---------------------------------------------------------------------------
def render(stations):
    st.header("Quelle offre de recharge est la plus adaptée à mes trajets ?")
    st.markdown(
        "Renseignez votre domicile (et, si vous le souhaitez, votre lieu de travail et un trajet "
        "récurrent) : l'application repère les bornes publiques autour de ces lieux et le long de vos "
        "trajets, identifie leurs opérateurs et compare abonnements et badges de recharge."
    )

    mode = st.radio(
        "Comment rechargez-vous sur les bornes publiques ?",
        ["Un seul type de recharge", "Mixte (plusieurs types)"], horizontal=True,
        help="En mode mixte, l'application cherche la meilleure combinaison d'abonnements : "
             "par exemple un réseau bon marché en AC près de chez vous et un abonnement "
             "ultra-rapide pour les longs trajets.",
    )

    with st.form("form_offres"):
        st.markdown("**📍 Lieux et trajets**")
        adresse = st.text_input("Adresse du domicile *", placeholder="ex. 20 avenue de Ségur, 75007 Paris")
        a1, a2 = st.columns(2)
        adresse_travail = a1.text_input("Lieu de travail (facultatif)", placeholder="ex. La Défense, Puteaux")
        allers_retours = a2.number_input("Allers-retours domicile ↔ travail par semaine", 0, 14, 5)
        b1, b2 = st.columns(2)
        adresse_dest = b1.text_input("Trajet récurrent : destination (facultatif)",
                                     placeholder="ex. maison de famille, résidence secondaire…")
        trajets_mois = b2.number_input("Allers-retours vers cette destination par mois", 0, 30, 1)
        c1, c2 = st.columns(2)
        rayon = c1.slider("Rayon autour du domicile / travail (km)", 1, 30, 5)
        corridor = c2.slider("Écart maximal au trajet (km)", 1, 20, 3,
                             help="Bornes situées à moins de X km de l'itinéraire routier.")

        st.markdown("**🚗 Véhicule et usage**")
        d1, d2, d3, d4 = st.columns(4)
        km_autres = d1.number_input("Autres km par semaine", 0, 3000, 100, step=10,
                                    help="Kilomètres hors trajets domicile-travail et trajet récurrent.")
        conso = d2.number_input("Consommation (kWh/100 km)", 10.0, 35.0, 17.0, step=0.5)
        batterie = d3.number_input("Capacité batterie (kWh)", 15, 150, 60, step=5)
        prise_rapide = d4.selectbox("Prise rapide du véhicule", list(moteur.PRISES_RAPIDES) + ["Aucune"])
        part_publique = st.slider("Part de l'énergie rechargée sur borne publique (%)", 0, 100, 50, step=5,
                                  help="Le reste est supposé rechargé à domicile ou au travail.")

        if mode == "Un seul type de recharge":
            palier = st.selectbox("Type de recharge publique", moteur.PALIERS, index=1,
                                  format_func=PALIER_LABELS.get)
            repartition = {p: (100 if p == palier else 0) for p in moteur.PALIERS}
        else:
            st.markdown("**Répartition de la recharge publique** (ramenée automatiquement à 100 %)")
            r1, r2, r3 = st.columns(3)
            repartition = {
                "AC": r1.number_input(PALIER_LABELS["AC"] + " (%)", 0, 100, 60, step=5),
                "DC": r2.number_input(PALIER_LABELS["DC"] + " (%)", 0, 100, 20, step=5),
                "HPC": r3.number_input(PALIER_LABELS["HPC"] + " (%)", 0, 100, 20, step=5),
            }
        lancer = st.form_submit_button("Trouver la meilleure offre", type="primary")

    if lancer:
        if not adresse.strip():
            st.warning("Merci de renseigner au moins l'adresse du domicile.")
            return
        if sum(repartition.values()) == 0:
            st.warning("La répartition entre types de recharge doit être supérieure à 0 %.")
            return
        with st.spinner("Géocodage des adresses et calcul des itinéraires…"):
            domicile = _localiser("Domicile", adresse)
            travail = _localiser("Lieu de travail", adresse_travail)
            dest = _localiser("Destination", adresse_dest)
            if False in (domicile, travail, dest):
                return
            routes = {}
            for nom, cible in (("Trajet domicile → travail", travail), ("Trajet récurrent", dest)):
                if cible:
                    routes[nom] = geo.itineraire(domicile[1], domicile[2], cible[1], cible[2])
        st.session_state["offres_params"] = dict(
            domicile=domicile, travail=travail, dest=dest, routes=routes,
            allers_retours=allers_retours, trajets_mois=trajets_mois, rayon=rayon, corridor=corridor,
            km_autres=km_autres, conso=conso, batterie=batterie, prise_rapide=prise_rapide,
            part_publique=part_publique, repartition=repartition,
        )

    params = st.session_state.get("offres_params")
    if params:
        _afficher_resultats(stations, **params)


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------
def _afficher_resultats(stations, domicile, travail, dest, routes, allers_retours, trajets_mois, rayon,
                        corridor, km_autres, conso, batterie, prise_rapide, part_publique, repartition):
    # --- Besoin énergétique
    km_semaine = km_autres
    if "Trajet domicile → travail" in routes:
        km_semaine += 2 * routes["Trajet domicile → travail"][1] * allers_retours
    if "Trajet récurrent" in routes:
        km_semaine += 2 * routes["Trajet récurrent"][1] * trajets_mois * 12 / 52
    energie_mois = km_semaine * 52 / 12 * conso / 100 * part_publique / 100
    total_rep = sum(repartition.values())
    energies = {p: energie_mois * v / total_rep for p, v in repartition.items()}
    nb_sessions = energie_mois / (0.7 * batterie)   # recharge typique de 10 % à 80 %

    lieux = {"Domicile": domicile[1:]}
    if travail:
        lieux["Travail"] = travail[1:]
    zone = geo.construire_zone(stations, lieux, {n: r[0] for n, r in routes.items()}, rayon, corridor)
    zone = moteur.restreindre_ac_aux_lieux(moteur.filtrer_compatibles(zone, prise_rapide))

    st.success("📍 " + " · ".join(f"{n} : {p[0]}" for n, p in
                                  (("Domicile", domicile), ("Travail", travail), ("Destination", dest)) if p))
    for nom, (_, dist, routier) in routes.items():
        st.caption(f"{nom} : {dist:.0f} km" + ("" if routier else
                   " (estimation à vol d'oiseau × 1,3 : service d'itinéraire indisponible)"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Distance hebdomadaire", f"{km_semaine:.0f} km")
    m2.metric("Énergie sur bornes publiques", f"{energie_mois:.0f} kWh/mois")
    m3.metric("Recharges publiques", f"≈ {nb_sessions:.1f} / mois", help="Une recharge = 10 % → 80 % de la batterie.")
    m4.metric("Points de charge compatibles", f"{len(zone):,}".replace(",", " "))

    if zone.empty:
        st.warning("Aucune borne publique compatible dans vos zones. Élargissez le rayon ou le corridor.")
        return
    if energie_mois <= 0:
        st.info("Aucune énergie à recharger sur borne publique avec ces paramètres.")
        return

    parts = moteur.parts_de_marche(zone)
    paniers, _ = moteur.simuler_paniers(parts, energies)

    # --- Recommandation
    best = paniers.iloc[0]
    st.subheader("🏆 Combinaison recommandée")
    st.markdown(f"**{best['Abonnement(s)']}** — environ **{best['Coût mensuel (€)']:.2f} € / mois** "
                f"(dont {best['dont frais fixes (€)']:.2f} € de frais fixes).")
    st.markdown("\n".join(f"- {ligne}" for ligne in best["Où recharger"]))
    if best["Économie vs sans abonnement (€/mois)"] > 0 and pd.notna(best["Rentable dès (kWh/mois)"]):
        st.caption(
            f"Économie de {best['Économie vs sans abonnement (€/mois)']:.2f} € / mois par rapport au paiement "
            f"sans abonnement. Rentable dès {best['Rentable dès (kWh/mois)']:.0f} kWh rechargés par mois — vous en "
            f"rechargez environ {energie_mois:.0f}. Comme une carte de cinéma : elle n'est intéressante que si "
            "vous y allez assez souvent pour que la réduction par séance rembourse la carte."
        )
    if best["non_reference"]:
        st.info("Pour " + ", ".join(PALIER_LABELS[p] for p in best["non_reference"]) +
                ", aucun réseau à tarif référencé n'est présent dans vos zones : le calcul utilise un prix moyen "
                "de marché. Un badge multi-réseaux (Chargemap, Electroverse…) permet d'y accéder.")

    st.subheader("Autres combinaisons possibles")
    st.dataframe(
        paniers.drop(columns=["non_reference", "nb"]).assign(
            **{"Où recharger": paniers["Où recharger"].map(lambda l: " | ".join(l))}),
        hide_index=True,
    )
    st.caption(
        "Chaque type de recharge est affecté au tarif le moins cher accessible dans vos zones, compte tenu des "
        "abonnements de la combinaison (au plus deux). La recharge lente (AC) n'est cherchée qu'autour du "
        "domicile et du travail, la recharge rapide aussi le long des trajets. Les badges payants à l'achat sont amortis sur 12 mois. "
        "Tarifs indicatifs hors frais d'occupation : vérifiez sur la grille de l'opérateur."
    )

    # --- Détail par palier
    with st.expander("Détail de toutes les offres, réseau par réseau"):
        for palier, e in energies.items():
            if e <= 0:
                continue
            st.markdown(f"**{PALIER_LABELS[palier]}** — {e:.0f} kWh/mois")
            detail = moteur.simuler_offres(parts, palier, e, nb_sessions * e / energie_mois)
            if detail.empty:
                st.write("Aucun réseau à tarif référencé pour ce type de recharge dans vos zones.")
            else:
                st.dataframe(detail, hide_index=True, column_config={
                    "Source": st.column_config.LinkColumn("Source", display_text="Grille tarifaire")})
        st.caption("Fiabilité du tarif : « officiel » = grille publiée par l'opérateur ; « indicatif » = presse "
                   "ou comparateurs ; « estimation » = prix affiché borne par borne, valeur moyenne estimée.")

    _afficher_operateurs(parts, zone)
    _afficher_carte(zone, parts, lieux, routes)


def _afficher_operateurs(parts, zone):
    st.subheader("Opérateurs présents dans vos zones")
    pivot = parts.pivot_table(index="operator_id", columns="palier", values="nb_pdc",
                              aggfunc="sum", fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
    pivot = pivot.rename(index=OPERATOR_LABELS, columns=PALIER_LABELS)
    g1, g2 = st.columns(2)
    g1.bar_chart(pivot, horizontal=True, stack=True, x_label="Points de charge", y_label="")
    resume = zone.groupby("operator_id").agg(
        Stations=("id_station_itinerance", "nunique"),
        pdc=("id_pdc_itinerance", "count"),
        proche=("distance_km", "min"),
        Zones=("zones", lambda z: ", ".join(sorted({x for s in z for x in s.split(", ")}))),
    ).reset_index().rename(columns={"pdc": "Points de charge", "proche": "Plus proche (km)"})
    resume["Part (%)"] = 100 * resume["Points de charge"] / resume["Points de charge"].sum()
    resume["Opérateur"] = resume["operator_id"].map(OPERATOR_LABELS)
    g2.dataframe(resume.sort_values("Points de charge", ascending=False)[
        ["Opérateur", "Stations", "Points de charge", "Part (%)", "Plus proche (km)", "Zones"]].round(1),
        hide_index=True)
    part_autre = resume.loc[resume["operator_id"] == "autre", "Part (%)"].sum()
    if part_autre > 0:
        st.caption(f"{part_autre:.0f} % des points de charge appartiennent à des opérateurs (souvent des réseaux "
                   "de collectivités) dont le tarif n'est pas référencé : ils restent généralement accessibles "
                   "avec un badge multi-réseaux.")


def _afficher_carte(zone, parts, lieux, routes):
    st.subheader("Carte des bornes compatibles")
    ops = list(dict.fromkeys(parts.sort_values("nb_pdc", ascending=False)["operator_id"]))
    couleur = {op: _hex_rgb(COULEURS[i % len(COULEURS)]) for i, op in enumerate(ops)}
    pts = zone[["lat", "lon", "operator_id", "puissance_nominale"]].copy()
    pts["color"] = pts["operator_id"].map(couleur)
    pts["info"] = (pts["operator_id"].map(OPERATOR_LABELS) + " — "
                   + pts["puissance_nominale"].round(0).astype(int).astype(str) + " kW")

    lieux_df = pd.DataFrame([{"lat": lat, "lon": lon, "info": nom} for nom, (lat, lon) in lieux.items()])
    chemins = pd.DataFrame([{"path": [list(c) for c in r[0]], "info": nom} for nom, r in routes.items()])

    layers = []
    if not chemins.empty:
        layers.append(pdk.Layer("PathLayer", chemins, get_path="path", get_color=[60, 60, 60],
                                width_min_pixels=3, pickable=True))
    layers.append(pdk.Layer("ScatterplotLayer", pts, get_position="[lon, lat]", get_fill_color="color",
                            get_radius=60, radius_min_pixels=3, pickable=True))
    layers.append(pdk.Layer("ScatterplotLayer", lieux_df, get_position="[lon, lat]", get_fill_color=[0, 0, 0],
                            get_radius=200, radius_min_pixels=8, pickable=True))
    vue = pdk.data_utils.compute_view(
        pd.concat([pts[["lon", "lat"]], lieux_df[["lon", "lat"]]]).values.tolist())
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=vue, map_provider="carto",
                             map_style=pdk.map_styles.CARTO_LIGHT, tooltip={"text": "{info}"}))
    st.markdown(" ".join(f"<span style='color:rgb({','.join(map(str, couleur[op]))})'>●</span> "
                         f"{OPERATOR_LABELS[op]}" for op in ops) + " · ⬤ Domicile / travail · — Trajets",
                unsafe_allow_html=True)
