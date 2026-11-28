L'objectif de ce dashboard est avant tout d'apprendre à utiliser Github et Streamlit, de la construction à la publication.
Les optimisations à réaliser sont nombreuses, notamment le code de l'application app.py est à nettoyer.


## Onglets de l'application

- **📊 Tableau de bord** : évolution des installations, répartition par opérateur ou puissance, carte filtrable.
- **💶 Quelle offre pour mes trajets ?** : à partir du domicile, du lieu de travail et d'un trajet récurrent
  (géocodage Base Adresse Nationale, itinéraire OpenRouteService / OSRM), l'application repère les bornes
  publiques compatibles autour des lieux (rayon) et le long des trajets (corridor), puis simule le coût mensuel
  des offres en mode « un seul type de recharge » ou « mixte » (meilleure combinaison de 0 à 2 abonnements).

Fichiers du comparateur :
- `recommandation.py` : interface.
- `moteur.py` : normalisation des bornes et calculs (coût mensuel, combinaisons, seuil de rentabilité).
- `geo.py` : géocodage, itinéraire et zones de recherche.
- `offres_recharge.py` : base des offres tarifaires avec leur niveau de fiabilité — à mettre à jour quand les tarifs changent.

### Clé OpenRouteService (itinéraires)
**Ne jamais écrire la clé dans le code.**
- En local : copier `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml` (ignoré par git).
- Sur Streamlit Community Cloud : *Settings → Secrets*, ajouter `ORS_API_KEY = "..."`.
