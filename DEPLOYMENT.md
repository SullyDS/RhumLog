# Déploiement RhumLog

RhumLog sépare volontairement le **portfolio public** de la **cave propriétaire persistante**.

## 1. Portfolio public — scénario recommandé

Le portfolio ne dépend d'aucun secret et ne publie pas la base SQLite personnelle.

```bash
RHUMLOG_APP_MODE=demo streamlit run app.py
```

Avec `RHUMLOG_APP_MODE=auto` — valeur par défaut — l'absence de `RHUMLOG_SOURCE_OWNER_ID` déclenche automatiquement le même comportement.

### Runtime public

Au démarrage :

1. `demo_data/*.csv` est lu ;
2. une base SQLite temporaire est reconstruite ;
3. l'identifiant runtime devient `demo` ;
4. `can_write=False` est forcé ;
5. les pages et actions propriétaire sont retirées de la navigation.

Le filesystem local du service n'est donc utilisé que comme **cache runtime reproductible**, jamais comme stockage métier persistant.

### Streamlit Community Cloud

Pour une démonstration portfolio :

- publier le dépôt GitHub ;
- sélectionner `app.py` comme point d'entrée ;
- aucun secret n'est nécessaire pour le mode public ;
- laisser le runtime en `auto`, ou forcer explicitement `demo` dans l'environnement si l'hébergeur le permet ;
- vérifier après déploiement que la sidebar indique bien **Démo publique · snapshot figé**.

Le stockage local d'un hébergement Streamlit éphémère ne doit pas être considéré comme persistant. C'est volontairement compatible avec le portfolio read-only.

## 2. Mode propriétaire / persistant

Pour conserver les écritures, il faut un environnement disposant d'un stockage persistant SQLite ou remplacer ultérieurement SQLite par une base distante.

Exemple `.env` local :

```env
RHUMLOG_APP_MODE=owner
RHUMLOG_DATABASE_PATH=/volume/rhumlog/rhumlog.sqlite
RHUMLOG_SOURCE_OWNER_ID=<private-owner-id>
RHUMLOG_OWNER_EMAIL=<owner-email>
RHUMLOG_DEV_OWNER=0
```

Pour l'authentification OIDC, utiliser `.streamlit/secrets.toml` à partir de `.streamlit/secrets.example.toml`. Le fichier réel est ignoré par Git.

`RHUMLOG_DEV_OWNER=1` doit rester limité au développement local.

## 3. Régénérer le snapshot portfolio

Après une évolution de la cave privée :

```bash
python scripts/build_demo_snapshot.py \
  --db data/rhumlog.sqlite \
  --owner-id "$RHUMLOG_SOURCE_OWNER_ID"
```

Puis :

```bash
python -m unittest discover -s tests -v
python scripts/smoke_public_demo.py
python scripts/release_check.py
```

Avant de committer `demo_data/`, relire son diff reste une bonne pratique même si les contrats automatisés passent.

## 4. Checklist avant publication

- [ ] `git status` propre ;
- [ ] aucun `.env` ou `secrets.toml` suivi par Git ;
- [ ] aucune base SQLite personnelle suivie ;
- [ ] tests unitaires OK ;
- [ ] smoke test public OK ;
- [ ] release check OK ;
- [ ] mode démo testé manuellement ;
- [ ] aucune action d'écriture visible en démo ;
- [ ] page À propos / Portfolio relue ;
- [ ] Model Card et métriques cohérentes avec le snapshot publié.
