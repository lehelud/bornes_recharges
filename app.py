import warnings
from datetime import datetime, timedelta

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from babel.dates import format_date
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

DATA_URL = "https://www.data.gouv.fr/fr/datasets/r/eb76d20a-8501-400e-b336-d85724de5435"
SHAPEFILE_PATH = "data/ARRONDISSEMENT.shp"
YEARS_WINDOW = 8
LAT_MIN, LAT_MAX = 41.5, 51.0
LON_MIN, LON_MAX = -5.0, 9.5
JOURS_FERIES_FIXES = ["01-01","05-01","05-08","07-14","08-15","11-01","11-11","12-25"]
plt.rcParams["font.family"] = "Montserrat"


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
    df_metro = df[df["consolidated_latitude"].between(LAT_MIN, LAT_MAX) & df["consolidated_longitude"].between(LON_MIN, LON_MAX)]
    return gpd.GeoDataFrame(df_metro, geometry=gpd.points_from_xy(df_metro["consolidated_longitude"], df_metro["consolidated_latitude"]), crs="EPSG:4326")


def _style_ax(ax):
    ax.grid(False)
    ax.spines[:].set_visible(False)


def plot_total_annuel(bornes_par_annee):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(bornes_par_annee.index.astype(str), bornes_par_annee.values, color="#1AA6A6", width=0.5)
    ax.set_title("Nombre total de bornes installees par annee")
    ax.set_xlabel("Annee")
    ax.set_ylabel("Nombre de bornes")
    _style_ax(ax)
    for i, v in enumerate(bornes_par_annee.values):
        ax.text(i, v, f"{v:,.0f}".replace(",", " "), ha="center", va="bottom")
    plt.tight_layout()
    return fig


def plot_moyenne_journaliere(results):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(results.index.astype(str), results["avg_per_working_day"], color="#007ACC", width=0.5)
    ax.set_title("Nombre moyen de bornes par jour ouvre")
    ax.set_xlabel("Annee")
    ax.set_ylabel("Moyenne / jour ouvre")
    _style_ax(ax)
    for i, v in enumerate(results["avg_per_working_day"]):
        ax.text(i, v, f"{v:.1f}", ha="center", va="bottom")
    plt.tight_layout()
    return fig


def plot_carte(gdf_stations, france):
    cmap = plt.cm.viridis
    norm = Normalize(vmin=gdf_stations["annee_mise_en_service"].min(), vmax=gdf_stations["annee_mise_en_service"].max())
    fig, ax = plt.subplots(figsize=(10, 10))
    france.plot(ax=ax, color="lightgray")
    gdf_stations.plot(ax=ax, markersize=5, column="annee_mise_en_service", cmap=cmap, norm=norm)
    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="Annee de mise en service")
    ax.set_title("Stations de recharge en France")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines[:].set_visible(False)
    plt.tight_layout()
    return fig


def afficher_header(df):
    date_max = pd.to_datetime(df["created_at"], errors="coerce", utc=True).max()
    date_affichee = format_date(date_max + timedelta(days=1), format="long", locale="fr")
    st.title("Bornes de recharge en France")
    st.caption(f"Donnees au {date_affichee} - mise a jour quotidienne")
    st.markdown("Source : [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/fichier-consolide-des-bornes-de-recharge-pour-vehicules-electriques/)")


def afficher_graphiques(results, bornes_par_annee):
    choix = st.radio("Graphique a afficher :", ["Nombre total de bornes par annee", "Moyenne par jour ouvre"])
    if choix == "Nombre total de bornes par annee":
        st.subheader("Nombre total de bornes installees par annee")
        st.pyplot(plot_total_annuel(bornes_par_annee))
    else:
        st.subheader("Moyenne de bornes par jour ouvre")
        st.pyplot(plot_moyenne_journaliere(results))


def afficher_carte(df, france, annees):
    st.subheader("Carte des stations de recharge")
    gdf = filtrer_france_metropolitaine(df[df["annee_mise_en_service"].isin(annees)])
    st.pyplot(plot_carte(gdf, france))


def main():
    st.set_page_config(page_title="Bornes de recharge", layout="wide")
    df = charger_donnees(DATA_URL)
    france = charger_geodata(SHAPEFILE_PATH)
    annee_courante = datetime.now().year
    annees = np.arange(annee_courante, annee_courante - YEARS_WINDOW, -1)
    results, bornes_par_annee = calculer_stats_annuelles(df, YEARS_WINDOW)
    afficher_header(df)
    afficher_graphiques(results, bornes_par_annee)
    afficher_carte(df, france, annees)


if __name__ == "__main__":
    main()
