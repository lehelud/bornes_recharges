import warnings
from datetime import datetime, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from babel.dates import format_date

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

DATA_URL = "https://www.data.gouv.fr/fr/datasets/r/eb76d20a-8501-400e-b336-d85724de5435"
SHAPEFILE_PATH = "data/ARRONDISSEMENT.shp"
YEARS_WINDOW = 8
LAT_MIN, LAT_MAX = 41.5, 51.0
LON_MIN, LON_MAX = -5.0, 9.5
JOURS_FERIES_FIXES = ["01-01","05-01","05-08","07-14","08-15","11-01","11-11","12-25"]

ANNEE_MIN = 2010
NON_RENSEIGNE = "Non renseignée"
AUTRES = "Autres opérateurs"
OPERATEUR_INCONNU = "Opérateur non renseigné"
CLASSES_PUISSANCE = [
    "Normale (≤ 7,4 kW)",
    "Accélérée (7,4 – 22 kW)",
    "Rapide (22 – 50 kW)",
    "Rapide (50 – 150 kW)",
    "Ultra-rapide (≥ 150 kW)",
    NON_RENSEIGNE,
]
COULEURS_PUISSANCE = ["#b5e0a8", "#4cb88f", "#1a8a8f", "#1f5a8a", "#3b1f6b", "#bdbdbd"]
COULEUR_AUTRES = "#bdbdbd"

COLOR_TEAL = "#1AA6A6"
COLOR_BLUE = "#007ACC"


def paques(annee):
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(114 + h + l - 7 * m, 31)
    return datetime(annee, mois, jour + 1)


def jours_feries_france(annee):
    p = paques(annee)
    feries_variables = [p + timedelta(days=1), p + timedelta(days=39), p + timedelta(days=50)]
    feries_fixes = [datetime(annee, int(d[:2]), int(d[3:])) for d in JOURS_FERIES_FIXES]
    return pd.DatetimeIndex(feries_fixes + feries_variables)


def nb_jours_ouvres(annee, jusqu_au=None):
    debut = datetime(annee, 1, 1)
    fin = jusqu_au if jusqu_au else datetime(annee + 1, 1, 1)
    jours = pd.bdate_range(start=debut, end=fin, inclusive="left")
    return len(jours.difference(jours_feries_france(annee)))


@st.cache_data(ttl=86_400, show_spinner="Chargement des donnees...")
def charger_donnees(url):
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    df = pd.read_csv(pd.io.common.BytesIO(response.content), low_memory=False)
    cols_date = df.filter(regex="date_|_at$").columns
    for col in cols_date:
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    df = df.dropna(subset=cols_date)
    df["annee_mise_en_service"] = pd.to_datetime(df["date_mise_en_service"], errors="coerce", utc=True).dt.year.astype("Int64")
    df["puissance_kw"] = convertir_puissance_kw(df["puissance_nominale"])
    df["classe_puissance"] = classer_puissance(df["puissance_kw"])
    df["operateur"] = nettoyer_operateur(df["nom_operateur"])
    return df


def nettoyer_operateur(noms):
    """Regroupe les variantes d'un même opérateur ('IZIVIA' / 'Izivia', 'SPBR1 | FR*EBN' / 'SPBR1')
    et garde l'orthographe la plus fréquente."""
    noms = noms.fillna(OPERATEUR_INCONNU).astype(str).str.split("|").str[0].str.strip()
    cle = noms.str.casefold().str.replace(r"[^0-9a-zà-ÿ]", "", regex=True)
    libelle = noms.groupby(cle).agg(lambda s: s.value_counts().index[0])
    return cle.map(libelle)


def convertir_puissance_kw(puissance):
    """Puissance en kW ; les valeurs >= 1000 sont supposées saisies en W."""
    p = pd.to_numeric(puissance, errors="coerce")
    return p.where(p < 1000, p / 1000)


def classer_puissance(puissance_kw):
    """Regroupe les puissances en 5 classes + 'Non renseignée' (valeur nulle ou absente)."""
    classes = pd.cut(
        puissance_kw,
        bins=[0, 7.4, 23, 49.99, 149.99, np.inf],  # 23 kW pour inclure les bornes déclarées à 22,08 kW
        labels=CLASSES_PUISSANCE[:-1],
    )
    return classes.cat.add_categories(NON_RENSEIGNE).fillna(NON_RENSEIGNE).astype(str)


@st.cache_data(show_spinner="Chargement du shapefile...")
def charger_geodata(shapefile_path):
    return gpd.read_file(shapefile_path).to_crs(epsg=4326)


def calculer_stats_annuelles(df, years_window):
    annee_courante = datetime.now().year
    annees = np.arange(annee_courante, annee_courante - years_window, -1)
    df_filtre = df[df["annee_mise_en_service"].isin(annees)]
    bornes_par_annee = df_filtre.groupby("annee_mise_en_service")["id_pdc_itinerance"].nunique()
    results = pd.DataFrame({"id_pdc_itinerance": bornes_par_annee})
    for annee in results.index:
        jours = nb_jours_ouvres(annee, jusqu_au=datetime.now()) if annee == annee_courante else nb_jours_ouvres(annee)
        results.loc[annee, "working_days"] = jours
    results["avg_per_working_day"] = results["id_pdc_itinerance"] / results["working_days"]
    return results, bornes_par_annee


def filtrer_france_metropolitaine(df):
    df_metro = df[
        df["consolidated_latitude"].between(LAT_MIN, LAT_MAX)
        & df["consolidated_longitude"].between(LON_MIN, LON_MAX)
    ].copy()
    return df_metro


# ---------------------------------------------------------------------------
# Graphiques Plotly interactifs
# ---------------------------------------------------------------------------

def plot_total_annuel(bornes_par_annee):
    df_plot = bornes_par_annee.reset_index()
    df_plot.columns = ["Annee", "Bornes"]
    df_plot["Annee"] = df_plot["Annee"].astype(str)
    fig = px.bar(
        df_plot,
        x="Annee",
        y="Bornes",
        text="Bornes",
        color_discrete_sequence=[COLOR_TEAL],
        title="Nombre total de bornes installees par annee",
        labels={"Annee": "Annee", "Bornes": "Nombre de bornes"},
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Bornes : %{y:,.0f}<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=False, zeroline=False),
        xaxis=dict(showgrid=False),
        hoverlabel=dict(bgcolor="white", font_size=13),
    )
    return fig


def plot_moyenne_journaliere(results):
    df_plot = results.reset_index()[["annee_mise_en_service", "avg_per_working_day"]]
    df_plot.columns = ["Annee", "Moyenne"]
    df_plot["Annee"] = df_plot["Annee"].astype(str)
    fig = px.bar(
        df_plot,
        x="Annee",
        y="Moyenne",
        text="Moyenne",
        color_discrete_sequence=[COLOR_BLUE],
        title="Nombre moyen de bornes installees par jour ouvre",
        labels={"Annee": "Annee", "Moyenne": "Moyenne / jour ouvre"},
    )
    fig.update_traces(
        texttemplate="%{text:.1f}",
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Moyenne : %{y:.1f} bornes/jour<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=False, zeroline=False),
        xaxis=dict(showgrid=False),
        hoverlabel=dict(bgcolor="white", font_size=13),
    )
    return fig


def couleurs_carte(df_filtre, couleur_par):
    """Retourne (colonne, ordre des modalités, couleurs) selon la variable choisie."""
    if couleur_par == "Puissance":
        ordre = [c for c in CLASSES_PUISSANCE if c in set(df_filtre["classe_puissance"])]
        couleurs = dict(zip(CLASSES_PUISSANCE, COULEURS_PUISSANCE))
        return "classe_puissance", ordre, [couleurs[c] for c in ordre]
    if couleur_par == "Opérateur":
        effectifs = df_filtre["operateur_carte"].value_counts()
        ordre = [a for a in effectifs.index if a != AUTRES] + ([AUTRES] if AUTRES in effectifs.index else [])
        palette = px.colors.qualitative.Alphabet
        couleurs = [COULEUR_AUTRES if a == AUTRES else palette[i % len(palette)] for i, a in enumerate(ordre)]
        return "operateur_carte", ordre, couleurs
    ordre = sorted(df_filtre["annee_str"].unique())
    couleurs = px.colors.sample_colorscale("Viridis", [i / max(len(ordre) - 1, 1) for i in range(len(ordre))])
    return "annee_str", ordre, couleurs


def plot_carte(df_filtre, couleur_par):
    colonne, ordre, couleurs = couleurs_carte(df_filtre, couleur_par)
    fig = px.scatter_map(
        df_filtre,
        lat="consolidated_latitude",
        lon="consolidated_longitude",
        color=colonne,
        category_orders={colonne: ordre},
        color_discrete_sequence=couleurs,
        custom_data=["operateur", "classe_puissance", "puissance_kw", "annee_str"],
        zoom=4.8,
        center={"lat": 46.5, "lon": 2.5},
        labels={"annee_str": "Année", "classe_puissance": "Puissance", "operateur_carte": "Opérateur"},
    )
    fig.update_traces(
        marker=dict(size=4),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Puissance : %{customdata[2]:.1f} kW (%{customdata[1]})<br>"
            "Mise en service : %{customdata[3]}<extra></extra>"
        ),
    )
    fig.update_layout(
        map_style="carto-positron",
        margin=dict(l=0, r=0, t=10, b=0),
        height=650,
        hoverlabel=dict(bgcolor="white", font_size=12),
        legend=dict(itemsizing="constant"),
        uirevision="carte",  # garde le zoom quand on change un filtre
    )
    return fig


def classement_operateurs(df):
    """Nombre de points de charge par opérateur, du plus grand au plus petit (hors non renseignés)."""
    return df["operateur"].value_counts().drop(OPERATEUR_INCONNU, errors="ignore")


def plot_top_operateurs(df_filtre, nb_top):
    top = classement_operateurs(df_filtre).head(nb_top).sort_values()
    fig = px.bar(
        x=top.values,
        y=top.index,
        orientation="h",
        text=top.values,
        color_discrete_sequence=[COLOR_TEAL],
        labels={"x": "Points de charge", "y": ""},
        title=f"Top {nb_top} des opérateurs (selon les filtres)",
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} points de charge<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=max(300, 28 * len(top) + 80),
        margin=dict(l=0, r=40, t=50, b=0),
    )
    return fig


# ---------------------------------------------------------------------------
# Interface Streamlit
# ---------------------------------------------------------------------------

def afficher_header(df):
    date_max = pd.to_datetime(df["created_at"], errors="coerce", utc=True).max()
    date_affichee = format_date(date_max + timedelta(days=1), format="long", locale="fr")
    st.title("Bornes de recharge en France")
    st.caption(f"Donnees au {date_affichee} - mise a jour quotidienne")
    st.markdown("Source : [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/fichier-consolide-des-bornes-de-recharge-pour-vehicules-electriques/)")


def afficher_kpis(df, bornes_par_annee):
    annee_courante = datetime.now().year
    total = int(df["id_pdc_itinerance"].nunique())
    cette_annee = int(bornes_par_annee.get(annee_courante, 0))
    annee_prec = int(bornes_par_annee.get(annee_courante - 1, 0))
    delta = f"+{cette_annee - annee_prec:,}" if annee_prec else "N/A"
    c1, c2, c3 = st.columns(3)
    c1.metric("Total bornes", f"{total:,}".replace(",", " "))
    c2.metric(f"Installees en {annee_courante}", f"{cette_annee:,}".replace(",", " "))
    c3.metric(f"vs {annee_courante - 1}", delta)


def afficher_graphiques(results, bornes_par_annee):
    choix = st.radio("Graphique a afficher :", ["Nombre total par annee", "Moyenne par jour ouvre"], horizontal=True)
    if choix == "Nombre total par annee":
        st.plotly_chart(plot_total_annuel(bornes_par_annee))
    else:
        st.plotly_chart(plot_moyenne_journaliere(results))


def afficher_carte(df):
    st.subheader("Carte interactive des points de charge")
    df_metro = filtrer_france_metropolitaine(df)
    df_metro = df_metro[df_metro["annee_mise_en_service"].between(ANNEE_MIN, datetime.now().year)].copy()
    df_metro["annee_str"] = df_metro["annee_mise_en_service"].astype(int).astype(str)
    annees_dispo = sorted(int(a) for a in df_metro["annee_mise_en_service"].unique())

    col1, col2 = st.columns(2)
    with col1:
        debut_defaut = max(annees_dispo[0], annees_dispo[-1] - YEARS_WINDOW + 1)
        annee_debut, annee_fin = st.select_slider(
            "Années de mise en service",
            options=annees_dispo,
            value=(debut_defaut, annees_dispo[-1]),
        )
    with col2:
        couleur_par = st.radio("Colorer par", ["Année", "Puissance", "Opérateur"], horizontal=True)
    puissances = st.multiselect("Puissance", CLASSES_PUISSANCE, default=CLASSES_PUISSANCE)

    df_filtre = df_metro[
        df_metro["annee_mise_en_service"].between(annee_debut, annee_fin)
        & df_metro["classe_puissance"].isin(puissances)
    ]

    col4, col5 = st.columns([1, 2])
    with col4:
        nb_top = st.slider("Nombre de plus grands opérateurs", 5, 25, 10)
    # Classement calculé sur toute la métropole pour que la liste reste stable quand on change les filtres
    top_operateurs = classement_operateurs(df_metro).head(nb_top).index.tolist()
    with col5:
        operateurs = st.multiselect(
            "Opérateurs (classés du plus grand au plus petit)",
            top_operateurs,
            help="Laisser vide pour afficher tous les opérateurs.",
        )

    if operateurs:
        df_filtre = df_filtre[df_filtre["operateur"].isin(operateurs)]
    df_filtre = df_filtre.assign(
        operateur_carte=df_filtre["operateur"].where(df_filtre["operateur"].isin(top_operateurs), AUTRES)
    )

    if df_filtre.empty:
        st.info("Aucun point de charge ne correspond à ces filtres.")
        return

    st.caption(f"{len(df_filtre):,} points de charge affichés".replace(",", " "))
    st.plotly_chart(plot_carte(df_filtre, couleur_par))
    st.plotly_chart(plot_top_operateurs(df_filtre, nb_top))

def main():
    st.set_page_config(page_title="Bornes de recharge", layout="wide")
    df = charger_donnees(DATA_URL)
    results, bornes_par_annee = calculer_stats_annuelles(df, YEARS_WINDOW)
    afficher_header(df)
    afficher_kpis(df, bornes_par_annee)
    st.divider()
    afficher_graphiques(results, bornes_par_annee)
    st.divider()
    afficher_carte(df)


if __name__ == "__main__":
    main()
