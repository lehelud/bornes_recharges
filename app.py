import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import geopandas as gpd
from datetime import datetime
from datetime import timedelta
import numpy as np
from babel.dates import format_date

plt.rcParams['font.family'] = 'Montserrat'

# URL du fichier
url = "https://www.data.gouv.fr/fr/datasets/r/eb76d20a-8501-400e-b336-d85724de5435"


# Télécharger le fichier
# response = requests.get(url)
def download_csv(url, file_path):
    try:
        # Send HTTP GET request to the URL
        response = requests.get(url)
        
        # Check if the request was successful (HTTP status code 200)
        if response.status_code == 200:
            # Open a file in write-binary mode to save the CSV content
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"File downloaded successfully and saved as {file_path}")
        else:
            print(f"Failed to download the file. Status code: {response.status_code}")
    
    except requests.RequestException as e:
        # Handle any exceptions that may occur during the request
        print(f"An error occurred: {e}")

# Local path where the CSV will be saved
file_path = 'downloaded_data.csv'

# Call the function to download the CSV
download_csv(url, file_path)

# Lire le contenu téléchargé directement en DataFrame
df = pd.read_csv(file_path, low_memory=False)
# df = pd.read_csv(StringIO(response.text), low_memory=False)

# Transformer toutes les colonnes contenant 'date' en datetime
# Use a regular expression to select columns to convert
date_columns = df.filter(regex='date_|_at$').columns
for col in date_columns:
    df[col] = pd.to_datetime(df[col])

annee_actuelle = datetime.now().year
vecteur_annee_inverse = np.arange(annee_actuelle, annee_actuelle - 1 - 7, -1)
df["annee_mise_en_service"] = df.date_mise_en_service.dt.year.astype('Int64')

# Compter le nombre unique de bornes installées par année
df_year=df[df['annee_mise_en_service'].isin(vecteur_annee_inverse)]

# Création d'un GeoDataFrame pour les coordonnées des stations
gdf_stations = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df['consolidated_longitude'], df['consolidated_latitude']),
    crs="EPSG:4326"  # Assurez-vous que c'est le bon système de référence
)

gdf_stations=gdf_stations[gdf_stations['annee_mise_en_service'].isin(vecteur_annee_inverse)]

chemin_du_shapefile = "data/ARRONDISSEMENT.shp"

# Lecture du shapefile avec geopandas
france_metropolitaine = gpd.read_file(chemin_du_shapefile)

france_metropolitaine = france_metropolitaine.to_crs(epsg=4326)

# if france_metropolitaine.crs is None:
#     france_metropolitaine.set_crs(epsg=4326, inplace=True)
# else:
#     france_metropolitaine = france_metropolitaine.to_crs(epsg=4326)

# Définition des limites géographiques approximatives de la France métropolitaine
latitude_min, latitude_max = 41.5, 51.0  # La Corse est approximativement au-dessus de 41.5° N
longitude_min, longitude_max = -5.0, 9.5  # La Corse est à moins de 9.5° E

# Filtrage des points en dehors des limites
gdf_stations_france = gdf_stations[
    (gdf_stations['consolidated_latitude'].between(latitude_min, latitude_max)) &
    (gdf_stations['consolidated_longitude'].between(longitude_min, longitude_max))
]


# Fonction pour générer le premier graphique (Bar Chart)
def plot_bar_chart(df_year):
    df_year['annee_mise_en_service'] = pd.to_datetime(df_year['date_mise_en_service']).dt.year
    bornes_par_annee = df_year.groupby('annee_mise_en_service')['id_pdc_itinerance'].nunique()

    plt.figure(figsize=(10, 6))
    plt.bar(bornes_par_annee.index.astype(str), bornes_par_annee.values, color='#1AA6A6', width=0.5)
    plt.title('Nombre total de bornes installées par année')
    plt.xlabel('Année')
    plt.ylabel('Nombre de bornes installées')
    plt.grid(False)
    plt.box(False)
    for index, value in enumerate(bornes_par_annee.values):
        plt.text(index, value, f'{value:,.0f}'.replace(',', ' '), ha='center', va='bottom')
    plt.tight_layout()
    return plt

# Fonction pour générer le second graphique (Carte)
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
    return plt

# Find the maximum date in the 'created_at' column
date_max_created_at = df['created_at'].max()
next_day = date_max_created_at + timedelta(days=1)
# Format the date in French
formatted_date = format_date(next_day, format='long', locale='fr')

# Streamlit UI
def main():
    title = f"Bornes de recharge en France \n Dashboard en construction (données au {formatted_date} - mise à jour quotidienne)"
    st.title(title)
    
    st.header("Nombre total de bornes installées par année")
    fig1 = plot_bar_chart(df_year)  # Assuming df_year and plot_bar_chart are defined elsewhere
    st.pyplot(fig1)

    st.header("Emplacement des stations de recharge en France")
    fig2 = plot_map(gdf_stations_france, france_metropolitaine)  # Assuming gdf_stations_france, france_metropolitaine and plot_map are defined elsewhere
    st.pyplot(fig2)

if __name__ == "__main__":
    main()