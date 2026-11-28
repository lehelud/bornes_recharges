L'objectif de ce dashboard est avant tout d'apprendre à utiliser Github et Streamlit, de la construction à la publication.
Les optimisations à réaliser sont nombreuses, notamment le code de l'application app.py est à nettoyer.


## Onglets de l'application

- **📊 Tableau de bord** : évolution du nombre de bornes installées et carte des stations (onglet historique).
- **💶 Quelle offre pour mon domicile ?** : à partir du domicile, du lieu de travail et d'un trajet récurrent
  (géocodage Base Adresse Nationale, itinéraire OSRM), l'application repère les bornes publiques compatibles
  autour des lieux (rayon) et le long des trajets (corridor), puis simule le coût mensuel des offres :
  - mode « un seul type de recharge » (AC, rapide ou ultra-rapide) ;
  - mode « mixte » : l'énergie est répartie entre les types de recharge et l'application cherche la meilleure
    combinaison de 0, 1 ou 2 abonnements. La recharge lente n'est cherchée qu'autour du domicile et du travail.

Fichiers :
- `recommandation.py` : interface du comparateur.
- `moteur.py` : normalisation des bornes et calculs (coût mensuel, combinaisons, seuil de rentabilité).
- `geo.py` : géocodage, itinéraire et zones de recherche (rayon / corridor).
- `offres_recharge.py` : base des offres tarifaires (CPO, réseaux locaux, eMSP) avec leur niveau de fiabilité — à mettre à jour quand les tarifs changent.
