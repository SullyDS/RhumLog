# Sécurité & confidentialité

## Modèle de confiance

RhumLog applique la lecture seule à deux niveaux :

1. l'interface masque les actions propriétaire lorsque `AccessContext.can_write` est faux ;
2. les méthodes de service mutantes appellent `require_write(...)` avant toute écriture SQLite.

La seconde couche est la barrière importante : masquer un bouton ne constitue jamais une autorisation.

## Modes runtime

### `demo`

- utilise uniquement le snapshot public ;
- n'utilise pas la base privée ;
- remplace l'identité propriétaire par `demo` ;
- force `can_write=False` ;
- ignore volontairement le raccourci développeur et l'identité OIDC pour l'autorisation d'écriture.

### `owner`

- utilise la base privée configurée ;
- nécessite un contrôle d'accès adapté avant exposition réseau ;
- doit disposer d'un stockage persistant pour conserver les écritures.

## Fichiers qui ne doivent jamais être publiés

- `.env` ;
- `.streamlit/secrets.toml` ;
- `data/*.sqlite`, `data/*.sqlite3`, `data/*.db` ;
- `private_exports/` ;
- exports SQL privés.

Ces chemins sont couverts par `.gitignore` et contrôlés de nouveau par `scripts/release_check.py` lorsqu'ils sont suivis par Git.

## Contrat du snapshot portfolio

Le script `scripts/build_demo_snapshot.py` :

- remappe les identifiants ;
- remplace l'identité propriétaire ;
- retire les lieux et notes libres de dégustation ;
- retire le texte source des profils sensoriels ;
- exclut les éléments placés en corbeille ;
- nettoie les anciennes descriptions ;
- conserve uniquement les variables nécessaires au produit public, à l'EDA et au pipeline ML.

Les tests vérifient notamment l'absence d'UUID historiques, d'adresses email et de champs libres interdits dans les CSV publics.

## Limites

Le snapshot contient volontairement des informations métier réelles non sensibles : noms de bouteilles, caractéristiques produit, scores de dégustation, prix et dates utiles à l'analyse. Il s'agit d'un choix de portfolio, pas d'un dataset fictif.

La revue humaine du diff de `demo_data/` reste recommandée avant publication.
