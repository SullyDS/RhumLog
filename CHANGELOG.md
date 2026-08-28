# Changelog

Les évolutions importantes de RhumLog sont documentées ici. Le projet utilise un versioning sémantique à partir de la release portfolio v3.

## [3.0.0] — Portfolio release

### Produit

- dashboard, collection, fiches bouteille et recommandations harmonisés ;
- design system sombre cognac et composants KPI responsives ;
- séparation claire entre pages Produit, Data Lab et outils propriétaire ;
- mode démo public en lecture seule.

### Data & Machine Learning

- EDA, Data Quality, corrélations et diversité documentées ;
- benchmark supervisé avec Leave-One-Out Cross Validation ;
- analyse des erreurs et feature engineering ;
- Ridge enrichi promu comme modèle final ;
- Model Card dynamique avec performance, provenance, couverture et limites ;
- MAE LOOCV de référence ≈ 0,644 et Spearman ≈ +0,650 sur 38 observations supervisées.

### Portfolio & sécurité

- snapshot public anonymisé et reproductible dans `demo_data/` ;
- contrôle d'accès en lecture seule à deux niveaux ;
- scripts de génération et de smoke test du snapshot public ;
- tests automatisés de confidentialité du dataset public ;
- CI GitHub ;
- documentation de déploiement et de sécurité.

## [2.7.x] — Public Demo

- runtime `auto | demo | owner` ;
- snapshot public anonymisé ;
- mode démo forcé en lecture seule ;
- documentation de déploiement ;
- corrections de lisibilité des KPI.

## [2.6.x] — UI/UX final polish

- design system premium ;
- harmonisation des pages Produit et Data Lab ;
- navigation et fiches bouteille retravaillées ;
- responsive et lisibilité renforcés.

## [2.0.x] — Data Science release

- consolidation du modèle final ;
- incertitude empirique ;
- Model Card ;
- export / sauvegarde ;
- pipeline sensoriel et qualité des données.

## [1.x] — Construction expérimentale

- migration vers Streamlit / SQLite ;
- analytics ;
- baseline de recommandation ;
- benchmarks ML ;
- analyse des erreurs ;
- feature engineering ;
- enrichissement sensoriel.
