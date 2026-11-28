"""Outils géographiques : géocodage (BAN), itinéraire (OSRM) et zones de recherche.

Une « zone » est l'ensemble des bornes utiles à l'utilisateur :
- un cercle de rayon R autour du domicile et du lieu de travail ;
- un corridor de largeur D de part et d'autre des trajets (domicile → travail,
  domicile → destination récurrente).
"""

import numpy as np
import pandas as pd
import requests
import shapely
import streamlit as st
from pyproj import Transformer

GEOCODERS = [
    "https://data.geopf.fr/geocodage/search",      # point d'accès actuel de la Base Adresse Nationale
    "https://api-adresse.data.gouv.fr/search/",    # ancien point d'accès
]
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

# Lambert-93 : projection officielle française, en mètres (calculs de distance précis)
_TO_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def geocode(adresse):
    """Renvoie (label, lat, lon) ou None."""
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


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def itineraire(lat1, lon1, lat2, lon2):
    """Itinéraire routier OSRM. Renvoie (liste de (lon, lat), distance_km, est_routier).

    En cas d'indisponibilité du service, on se rabat sur la ligne droite
    (distance × 1,3, ordre de grandeur habituel du détour routier).
    """
    try:
        resp = requests.get(
            OSRM_URL.format(lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2),
            params={"overview": "full", "geometries": "geojson"}, timeout=10,
        )
        if resp.status_code == 200:
            route = resp.json()["routes"][0]
            return [tuple(c) for c in route["geometry"]["coordinates"]], route["distance"] / 1000, True
    except (requests.RequestException, ValueError, KeyError, IndexError):
        pass
    vol = haversine_km(lat1, lon1, np.array([lat2]), np.array([lon2]))[0]
    return [(lon1, lat1), (lon2, lat2)], vol * 1.3, False


def haversine_km(lat, lon, lats, lons):
    """Distance à vol d'oiseau (km) entre un point et un vecteur de points."""
    lat1, lon1 = np.radians(lat), np.radians(lon)
    lat2, lon2 = np.radians(lats), np.radians(lons)
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _bbox(stations, lat_min, lat_max, lon_min, lon_max, marge_km):
    dlat = marge_km / 111.0
    dlon = marge_km / (111.0 * max(np.cos(np.radians((lat_min + lat_max) / 2)), 0.1))
    return stations[stations["lat"].between(lat_min - dlat, lat_max + dlat)
                    & stations["lon"].between(lon_min - dlon, lon_max + dlon)]


def autour_point(stations, lat, lon, rayon_km):
    """Distances (km) des bornes situées à moins de rayon_km du point."""
    proche = _bbox(stations, lat, lat, lon, lon, rayon_km)
    d = pd.Series(haversine_km(lat, lon, proche["lat"].values, proche["lon"].values), index=proche.index)
    return d[d <= rayon_km]


def le_long_trajet(stations, coords, corridor_km):
    """Distances (km) au trajet des bornes situées dans le corridor."""
    lons, lats = zip(*coords)
    proche = _bbox(stations, min(lats), max(lats), min(lons), max(lons), corridor_km)
    if proche.empty:
        return pd.Series(dtype=float)
    lx, ly = _TO_L93.transform(np.array(lons), np.array(lats))
    ligne = shapely.LineString(np.column_stack([lx, ly]))
    px, py = _TO_L93.transform(proche["lon"].values, proche["lat"].values)
    d = pd.Series(shapely.distance(shapely.points(px, py), ligne) / 1000, index=proche.index)
    return d[d <= corridor_km]


def construire_zone(stations, lieux, trajets, rayon_km, corridor_km):
    """Assemble les bornes de toutes les zones.

    lieux   : dict {nom: (lat, lon)}         → cercle de rayon_km
    trajets : dict {nom: liste de (lon,lat)} → corridor de corridor_km
    Renvoie les bornes avec `distance_km` (distance au lieu/trajet le plus proche)
    et `zones` (noms des zones concernées).
    """
    morceaux = []
    for nom, (lat, lon) in lieux.items():
        d = autour_point(stations, lat, lon, rayon_km)
        morceaux.append(pd.DataFrame({"distance_km": d, "zone": nom}))
    for nom, coords in trajets.items():
        d = le_long_trajet(stations, coords, corridor_km)
        morceaux.append(pd.DataFrame({"distance_km": d, "zone": nom}))
    morceaux = [m for m in morceaux if not m.empty]
    if not morceaux:
        return stations.iloc[0:0].assign(distance_km=pd.Series(dtype=float), zones=pd.Series(dtype=str))
    tout = pd.concat(morceaux)
    agg = tout.groupby(level=0).agg(
        distance_km=("distance_km", "min"),
        zones=("zone", lambda z: ", ".join(dict.fromkeys(z))),
    )
    return stations.loc[agg.index].join(agg)
