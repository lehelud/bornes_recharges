L'objectif de ce dashboard est avant tout d'apprendre à utiliser Github et Streamlit, de la construction à la publication.
Les optimisations à réaliser sont nombreuses, notamment le code de l'application app.py est à nettoyer.


## Onglets de l'application

- **📊 Tableau de bord** : évolution du nombre de bornes installées et carte des stations (onglet historique).
- **💶 Quelle offre pour mon domicile ?** : à partir d'une adresse (géocodée via la Base Adresse Nationale),
  l'application repère les bornes publiques compatibles dans un rayon donné, calcule la part de chaque
  opérateur et simule le coût mensuel de chaque offre (abonnements opérateurs et badges multi-réseaux)
  pour recommander la plus rentable, avec son seuil de rentabilité.

Fichiers :
- `recommandation.py` : moteur de calcul et interface du comparateur.
- `offres_recharge.py` : base des offres tarifaires (CPO & eMSP) et normalisation des opérateurs — à mettre à jour quand les tarifs changent.
