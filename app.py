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
    return df


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


def plot_carte(df_metro, annees):
    df_filtre = df_metro[df_metro["annee_mise_en_service"].isin(annees)].copy()
    df_filtre["annee_str"] = df_filtre["annee_mise_en_service"].astype(str)
    fig = px.scatter_mapbox(
        df_filtre,
        lat="consolidated_latitude",
        lon="consolidated_longitude",
        color="annee_str",
        hover_name="nom_amenageur" if "nom_amenageur" in df_filtre.columns else None,
        hover_data={
            "consolidated_latitude": False,
            "consolidated_longitude": False,
            "annee_str": True,
        },
        color_discrete_sequence=px.colors.sequential.Viridis,
        zoom=4.8,
        center={"lat": 46.5, "lon": 2.5},
        title="Stations de recharge en France",
        labels={"annee_str": "Annee"},
    )
    fig.update_traces(marker=dict(size=4), hovertemplate="<b>%{hovertext}</b><br>Annee : %{marker.color}<extra></extra>")
    fig.update_layout(
        mapbox_style="carto-positron",
        margin=dict(l=0, r=0, t=40, b=0),
        height=600,
        hoverlabel=dict(bgcolor="white", font_size=12),
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
        st.plotly_chart(plot_total_annuel(bornes_par_annee), use_container_width=True)
    else:
        st.plotly_chart(plot_moyenne_journaliere(results), use_container_width=True)


def afficher_carte(df, annees):
    st.subheader("Carte interactive des stations")
    df_metro = filtrer_france_metropolitaine(df)
    st.plotly_chart(plot_carte(df_metro, annees), use_container_width=True)


def main():
    st.set_page_config(page_title="Bornes de recharge", layout="wide")
    df = charger_donnees(DATA_URL)
    annee_courante = datetime.now().year
    annees = np.arange(annee_courante, annee_courante - YEARS_WINDOW, -1)
    results, bornes_par_annee = calculer_stats_annuelles(df, YEARS_WINDOW)
    afficher_header(df)
    afficher_kpis(df, bornes_par_annee)
    st.divider()
    afficher_graphiques(results, bornes_par_annee)
    st.divider()
    afficher_carte(df, annees)


if __name__ == "__main__":
    main()
