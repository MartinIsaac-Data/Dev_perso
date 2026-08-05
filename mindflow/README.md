# MindFlow AI

Capturer une pensée à la voix en moins de trois secondes, et la retrouver
transformée en note, en tâche ou en rendez-vous — sans avoir eu à choisir
laquelle.

La conception, les décisions d'architecture et le plan de déploiement sont dans
[`../docs/`](../docs/). Ce fichier ne répond qu'à une question : comment le
faire tourner.

---

## Démarrer

```bash
./tool/dev_up.sh
```

Le script crée le rôle et la base, pose l'extension `pgvector`, applique les
neuf migrations, démarre le worker puis l'API, et n'affiche « MindFlow tourne »
qu'après avoir vu `/health` répondre et le worker annoncer ses tâches. Le
relancer ne recrée rien.

| Commande | Effet |
| --- | --- |
| `./tool/dev_up.sh` | Démarre tout et vérifie |
| `./tool/dev_up.sh --stop` | Arrête l'API et le worker (PostgreSQL et Redis restent) |
| `./tool/dev_up.sh --token` | Imprime un jeton de développement |

Il faut au préalable **PostgreSQL 16 avec `pgvector`**, **Redis 7** et
[`uv`](https://astral.sh/uv). Le script vérifie les trois et dit quoi faire
s'il en manque un.

Ensuite le client :

```bash
cd frontend && MINDFLOW_API_BASE_URL=http://127.0.0.1:8000 ./tool/build.sh linux   # ou: web
```

## Aucune clé n'est nécessaire, et c'est temporaire

En local, les jetons ne sont pas signés et les moteurs de parole et de langage
sont des simulations qui renvoient du texte français plausible, hors ligne. Les
deux sont refusés dès que `MINDFLOW_ENV` n'est plus `local` — le contrôle de
configuration ne démarre pas avec.

**Le faux encodeur mérite un avertissement à part** : ses vecteurs s'indexent et
se retrouvent *avec succès*, et n'encodent rien. La recherche sémantique aura
l'air de fonctionner en renvoyant les mauvaises notes. Pour de vrais résultats,
renseignez `MINDFLOW_STT_BACKEND`, `MINDFLOW_LLM_BACKEND` et la clé
correspondante dans `backend/.env`.

## Développer

```bash
cd backend
uv run pytest                    # 896 tests ; ceux qui touchent la base sont
                                 # ignorés si MINDFLOW_TEST_DATABASE_URL ne
                                 # pointe pas sur un PostgreSQL joignable
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run lint-imports              # 5 contrats de dépendances entre couches

cd ../frontend
flutter test && flutter analyze
node tool/smoke_web.mjs          # démarre le build web dans un Chromium,
                                 # coupe le réseau, vérifie qu'il survit
```

## Ce qui n'a jamais tourné

Énoncé plutôt qu'omis, et détaillé dans [`../docs/TODO.md`](../docs/TODO.md)
§6 ter : aucun déploiement (ni Docker Compose, ni Kubernetes), aucune
restauration de sauvegarde, aucun test de charge, aucun appel réel à un
fournisseur d'IA ou d'intégration, aucune réunion réelle transcrite, aucun
binaire Windows ni macOS.
