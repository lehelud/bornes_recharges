import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import geopandas as gpd
from datetime import datetime, timedelta
import numpy as np
from babel.dates import format_date
from pandas.tseries.holiday import USFederalHolidayCalendar as Calendar

plt.rcParams['font.family'] = 'Montserrat'

# URL du fichier
url = "https://www.data.gouv.fr/fr/datasets/r/eb76d20a-8501-400e-b336-d85724de5435"

# Fonction pour télécharger le CSV
def download_csv(url, file_path):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"File downloaded successfully and saved as {file_path}")
        else:
            print(f"Failed to download the file. Status code: {response.status_code}")
    except requests.RequestException as e:
        print(f"An error occurred: {e}")

# Local path where the CSV will be saved
file_path = 'downloaded_data.csv'

# Call the function to download the CSV
download_csv(url, file_path)

# Lire le contenu téléchargé directement en DataFrame
df = pd.read_csv(file_path, low_memory=False)

# Transformer toutes les colonnes date en datetime
date_columns = df.filter(regex='date_|_at$').columns
for col in date_columns:
    df[col] = pd.to_datetime(df[col], errors='coerce')  # Ajout de errors='coerce' pour éviter les erreurs sur les dates hors limites

# Filtrer les dates non valides
df = df.dropna(subset=date_columns)

annee_actuelle = datetime.now().year
vecteur_annee_inverse = np.arange(annee_actuelle, annee_actuelle - 1 - 7, -1)
df["annee_mise_en_service"] = pd.to_datetime(df['date_mise_en_service'], errors='coerce').dt.year.astype('Int64')

# Compter le nombre unique de bornes installées par année
df_year = df[df['annee_mise_en_service'].isin(vecteur_annee_inverse)]

# Calcul du nombre moyen d'installation par jour ouvré
df_nb_id_year = df_year.groupby('annee_mise_en_service')['id_pdc_itinerance'].nunique()

# Create a DataFrame to store results
results = pd.DataFrame(df_nb_id_year, columns=['id_pdc_itinerance'])

# Calculate number of working days per year, excluding federal US holidays
workdays_per_year = {}
years = results.index
for year in years:
    all_days = pd.date_range(start=str(year), end=str(year + 1), inclusive='left', freq='B')
    holidays = Calendar().holidays(start=all_days.min(), end=all_days.max())
    workdays = all_days.difference(holidays)
    workdays_per_year[year] = len(workdays)

results['working_days'] = pd.Series(workdays_per_year)
results['avg_per_working_day'] = results['id_pdc_itinerance'] / results['working_days']

# Get the current year
current_year = datetime.now().year

# Check if the current year is in the results and adjust for a partial year
if current_year in results.index:
    today = datetime.now()
    all_days = pd.date_range(start=f'{current_year}-01-01', end=today, inclusive='left', freq='B')
    holidays = Calendar().holidays(start=all_days.min(), end=all_days.max())
    workdays = all_days.difference(holidays)
    results.at[current_year, 'working_days'] = len(workdays)
    results.at[current_year, 'avg_per_working_day'] = results.at[current_year, 'id_pdc_itinerance'] / len(workdays)

bornes_par_annee = df_year.groupby('annee_mise_en_service')['id_pdc_itinerance'].nunique()

# Création d'un GeoDataFrame pour les coordonnées des stations
gdf_stations = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['consolidated_longitude'], df['consolidated_latitude']),
    crs="EPSG:4326"
)

gdf_stations = gdf_stations[gdf_stations['annee_mise_en_service'].isin(vecteur_annee_inverse)]

chemin_du_shapefile = "data/ARRONDISSEMENT.shp"

# Lecture du shapefile avec geopandas
france_metropolitaine = gpd.read_file(chemin_du_shapefile)
france_metropolitaine = france_metropolitaine.to_crs(epsg=4326)

# Définition des limites géographiques approximatives de la France métropolitaine
latitude_min, latitude_max = 41.5, 51.0
longitude_min, longitude_max = -5.0, 9.5

# Filtrage des points en dehors des limites
gdf_stations_france = gdf_stations[
    (gdf_stations['consolidated_latitude'].between(latitude_min, latitude_max)) &
    (gdf_stations['consolidated_longitude'].between(longitude_min, longitude_max))
]

# Fonction pour générer le graphique du nombre moyen de borne par année
def plot_avg_per_working_day(results):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(results.index.astype(str), results['avg_per_working_day'], color='#007ACC', width=0.5)
    ax.set_title('Nombre moyen de bornes installées par jour ouvré par année')
    ax.set_xlabel('Année')
    ax.set_ylabel('Moyenne par jour ouvré')
    plt.grid(False)
    plt.box(False)
    for index, value in enumerate(results['avg_per_working_day']):
        ax.text(index, value, f'{value:.1f}', ha='center', va='bottom')
    plt.tight_layout()
    return fig

# Fonction pour générer le graphique du nombre total de borne par année
def plot_bar_chart(df_year):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(bornes_par_annee.index.astype(str), bornes_par_annee.values, color='#1AA6A6', width=0.5)
    ax.set_title('Nombre total de bornes installées par année')
    ax.set_xlabel('Année')
    ax.set_ylabel('Nombre de bornes installées')
    plt.grid(False)
    plt.box(False)
    for index, value in enumerate(bornes_par_annee.values):
        ax.text(index, value, f'{value:,.0f}'.replace(',', ' '), ha='center', va='bottom')
    plt.tight_layout()
    return fig

# Fonction pour générer le graphique de la carte
def plot_map(gdf_stations_france, france_metropolitaine):
    cmap = plt.cm.viridis
    norm = Normalize(vmin=gdf_stations_france['annee_mise_en_service'].min(), vmax=gdf_stations_france['annee_mise_en_service'].max())
    fig, ax = plt.subplots(figsize=(10, 10))
    france_metropolitaine.plot(ax=ax, color='lightgray')
    gdf_stations_france.plot(ax=ax, markersize=5, column='annee_mise_en_service', cmap=cmap, legend=False, norm=norm)
    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label('Année de Mise en Service')
    plt.grid(False)
    plt.box(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title('Emplacement des stations de recharge en France')
    plt.tight_layout()
    return fig

# Formater la date en français
date_max_created_at = pd.to_datetime(df['created_at'], errors='coerce').max()
next_day = date_max_created_at + timedelta(days=1)
formatted_date = format_date(next_day, format='long', locale='fr')

# Streamlit UI
def main():
    title = f"Bornes de recharge en France \n Dashboard en construction (données au {formatted_date} - mise à jour quotidienne)"
    st.title(title)
    st.markdown("Source des données: [Fichier consolidé des bornes de recharge pour véhicules électriques](https://www.data.gouv.fr/fr/datasets/fichier-consolide-des-bornes-de-recharge-pour-vehicules-électriques/)")
    chart_type = st.radio(
        "Choisissez le type de graphique à afficher:",
        ('Nombre total de bornes installées par année', 'Nombre moyen de bornes installées par jour ouvré')
    )
    if chart_type == 'Nombre total de bornes installées par année':
        st.header("Nombre total de bornes installées par année")
        fig1 = plot_bar_chart(df_year)
        st.pyplot(fig1)
    else:
        st.header("Nombre moyen de bornes installées par jour ouvré")
        fig2 = plot_avg_per_working_day(results)
        st.pyplot(fig2)
    st.header("Emplacement des stations de recharge en France")
    fig3 = plot_map(gdf_stations_france, france_metropolitaine)
    st.pyplot(fig3)

if __name__ == "__main__":
    main()
