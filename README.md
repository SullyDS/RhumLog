# RhumLog — Personal Rum Data Product

RhumLog est un projet personnel que j'ai fait évoluer d'une simple application de gestion de cave vers un **Data Product complet** : modélisation métier, analytics, qualité des données, Machine Learning explicable, Model Card et démonstration publique en lecture seule. Le lien est :https://rhumlog-portfolio.streamlit.app/

<img width="1610" height="1232" alt="image" src="https://github.com/user-attachments/assets/8d276e5e-cddb-4620-a56a-47db60898e6e" />
<img width="2514" height="1296" alt="image" src="https://github.com/user-attachments/assets/5973eb61-0b40-4fef-a5a3-3397701031fa" />


> **Question Data Science :** peut-on estimer mon appréciation d'un rhum avant dégustation en utilisant uniquement des informations disponibles à t0 ?

## En un coup d'œil

| Dimension | État de référence |
| --- | ---: |
| Références | 59 |
| Dégustations | 38 |
| Observations supervisées | 38 |
| Modèle final | Ridge enrichi |
| Validation | Leave-One-Out Cross Validation |
| MAE LOOCV | ≈ 0,644 / 10 |
| Spearman | ≈ +0,650 |
| Top hauts scores | 7 / 10 |

Ces métriques décrivent un **petit dataset personnel**. Elles servent à évaluer le protocole et la qualité relative des modèles, pas à prétendre à une généralisation à d'autres dégustateurs.

## Ce que montre le projet

### Produit

- dashboard de suivi de la cave ;
- collection filtrable et fiches bouteille ;
- carnet de dégustation ;
- recommandations sur les bouteilles déjà connues du système ;
- file de données à documenter ;
- mode propriétaire avec écriture et mode portfolio public read-only.

### Data & Analytics

- EDA collection / dégustations ;
- Pearson, Spearman et Shannon normalisé ;
- analyse prix ↔ plaisir et sweet spot documenté ;
- profil aromatique et diversité ;
- règles explicites de Data Quality ;
- storytelling qui évite de fabriquer des tendances temporelles non étayées.

### Machine Learning

Le développement du modèle suit une logique expérimentale plutôt qu'une course à la complexité :

```text
baseline heuristique
        ↓
benchmark Ridge / ElasticNet / k-NN / Random Forest
        ↓
validation LOOCV
        ↓
analyse des erreurs
        ↓
feature engineering
        ↓
Ridge enrichi promu
        ↓
incertitude empirique + Model Card
```

Le preprocessing est réalisé dans les pipelines de validation pour limiter les fuites d'information. Les variables post-dégustation susceptibles de créer du target leakage restent exclues du modèle prédictif.

## Pourquoi Ridge au final ?

Random Forest a d'abord obtenu de bons résultats, mais l'analyse des prédictions a montré une forte compression vers la moyenne. Plutôt que d'augmenter immédiatement la complexité algorithmique, j'ai travaillé sur la **représentation des données** : âge, origine et dimensions sensorielles documentées.

Le Ridge enrichi a ensuite amélioré la validation hors-échantillon tout en conservant une forte interprétabilité. Le choix final repose donc sur un compromis **performance / stabilité / explicabilité**, pas sur la sophistication du nom de l'algorithme.

## Architecture

```text
┌──────────────────────────────────────────────────────┐
│                     STREAMLIT UI                     │
│ Dashboard · Collection · Recommandations · Data Lab │
└──────────────────────────┬───────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│                  SERVICES PYTHON                     │
│ Métier · Analytics · Data Quality · ML · Export     │
└───────────────────┬────────────────────┬─────────────┘
                    │                    │
                    ▼                    ▼
        ┌────────────────────┐   ┌────────────────────┐
        │       SQLite       │   │   scikit-learn    │
        │ rums               │   │ Pipeline          │
        │ tastings           │   │ Ridge             │
        │ sensory_profiles   │   │ LOOCV             │
        └────────────────────┘   └────────────────────┘
```

### Stack

`Python 3.12` · `Streamlit` · `pandas` · `Plotly` · `SQLite` · `scikit-learn`

## Mode portfolio public

Le dépôt est conçu pour pouvoir être cloné et lancé **sans `.env`, sans base personnelle et sans secret**.

```bash
git clone <repository-url>
cd rhumlog-streamlit
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Avec la configuration par défaut, RhumLog utilise automatiquement le snapshot anonymisé de `demo_data/` et force la lecture seule.

Pour tester explicitement ce mode :

```bash
RHUMLOG_APP_MODE=demo streamlit run app.py
```

## Snapshot public & confidentialité

`demo_data/` est un artefact public versionné. Sa construction :

- remappe les identifiants historiques en `demo-rum-XXX` ;
- remplace l'identifiant propriétaire par `demo` ;
- retire les lieux de dégustation ;
- retire les notes libres de dégustation ;
- retire les textes sources sensoriels ;
- exclut la corbeille ;
- conserve les variables nécessaires à l'EDA et au pipeline ML.

La base SQLite personnelle n'est jamais nécessaire au portfolio public.

## Utiliser la cave privée en local

Créer `.env` à partir de `.env.example` :

```env
RHUMLOG_APP_MODE=owner
RHUMLOG_DATABASE_PATH=data/rhumlog.sqlite
RHUMLOG_SOURCE_OWNER_ID=<private-owner-id>
RHUMLOG_DEV_OWNER=1
```

`RHUMLOG_DEV_OWNER=1` sert uniquement au développement local. Pour un environnement propriétaire exposé, utiliser l'authentification OIDC et un stockage persistant.

## Régénérer le snapshot public

```bash
python scripts/build_demo_snapshot.py \
  --db data/rhumlog.sqlite \
  --owner-id "$RHUMLOG_SOURCE_OWNER_ID"
```

Puis exécuter les contrôles avant commit :

```bash
python -m compileall -q app.py rhumlog scripts tests
python -m unittest discover -s tests -v
python scripts/smoke_public_demo.py
python scripts/release_check.py
```

## Structure du dépôt

```text
rhumlog/
├── pages/        # pages Produit, Analytics et Data Lab
├── services/     # logique métier, analytics, ML, qualité et export
├── ui/           # design system Streamlit
├── access.py     # contrat de lecture / écriture
├── config.py     # modes auto / demo / owner
├── db.py         # schéma SQLite
└── demo.py       # reconstruction du runtime public

demo_data/        # snapshot public anonymisé
scripts/          # import, génération snapshot, smoke/release checks
tests/            # contrats runtime et confidentialité
```

## Limites assumées

- seulement 38 observations supervisées dans le snapshot actuel ;
- peu de dégustations répétées d'un même rhum ;
- couverture sensorielle partielle ;
- certaines catégories peu représentées ;
- incertitude affichée de nature empirique et globale ;
- modèle strictement personnel, sans prétention de généralisation.

Ces limites sont affichées dans l'application et font partie de la Model Card : elles ne sont pas masquées pour embellir les résultats.

## Documentation

- [`DEPLOYMENT.md`](DEPLOYMENT.md) — modes public / propriétaire et stratégie d'hébergement ;
- [`SECURITY.md`](SECURITY.md) — modèle de confiance et contrat de données publiques ;
- [`CHANGELOG.md`](CHANGELOG.md) — historique des grandes étapes du projet ;
- [`.streamlit/secrets.example.toml`](.streamlit/secrets.example.toml) — exemple OIDC sans credentials réels.

## Données privées à ne jamais committer

`.env` · `.streamlit/secrets.toml` · `data/*.sqlite` · `private_exports/` · exports SQL privés
