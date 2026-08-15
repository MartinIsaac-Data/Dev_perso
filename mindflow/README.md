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
| `./tool/dev_up.sh --web` | Construit le client web et le sert sur `127.0.0.1:8080` |
| `./tool/dev_up.sh --lan` | Écoute sur le réseau local, pour qu'un téléphone joigne l'API |
| `./tool/dev_up.sh --stop` | Arrête l'API, le worker et le client web |
| `./tool/dev_up.sh --token` | Imprime un jeton de développement |

**`--lan` ouvre l'API au réseau, et cela se paie.** En environnement `local` les
jetons ne sont pas vérifiés : sur `127.0.0.1` cela n'engage que votre machine,
sur le réseau cela signifie que quiconque atteint le port peut lire et écrire
toutes vos notes. À réserver à un réseau de confiance, et à couper ensuite. Le
script vous le rappelle à chaque démarrage.

`--lan` sert à ce que l'application Android trouve le serveur, pas à capturer
depuis le navigateur d'un téléphone : celui-ci refusera le micro sur une IP en
clair, faute de contexte sécurisé.

`--web` est le chemin le plus court pour utiliser le produit : ouvrez
`http://127.0.0.1:8080`, connectez-vous avec n'importe quelle adresse, et
enregistrez. Le service est servi sur `localhost` parce que le micro n'est
accordé qu'en contexte sécurisé — HTTPS ou `localhost` ; sur une IP de LAN en
clair, l'application s'ouvre et ne peut rien enregistrer.

Il faut au préalable **PostgreSQL 16 avec `pgvector`**, **Redis 7** et
[`uv`](https://astral.sh/uv). Le script vérifie les trois et dit quoi faire
s'il en manque un.

Les autres cibles, depuis `frontend/` :

| Cible | Commande | État |
| --- | --- | --- |
| Web | `./tool/build.sh web` | Construit et vérifié, micro compris |
| Linux | `./tool/build.sh linux` | Construit ; **n'enregistre pas** sans `fmedia`, absent des dépôts Debian et abandonné en amont |
| Android | `./tool/build.sh android` | Configuré — autorisations, désugarage, `minSdk 23` — et **jamais compilé** ici, faute de SDK |
| Windows, macOS | `./tool/build.sh windows` / `macos` | Demandent l'hôte correspondant ; Flutter ne compile pas en croisé |

`MINDFLOW_API_BASE_URL` est figée à la construction. Sur un téléphone,
`localhost` désigne le téléphone : passez l'adresse de cette machine sur le
réseau local, ou `10.0.2.2` depuis l'émulateur Android.

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
node tool/e2e_capture.mjs        # enregistre réellement au micro dans un
                                 # navigateur et suit la capture jusqu'à
                                 # l'entrée créée (pile locale requise)
node tool/check_android.mjs      # ce que le manifeste et le Gradle doivent
                                 # contenir, à défaut de pouvoir compiler
```

## Ce qui n'a jamais tourné

Énoncé plutôt qu'omis, et détaillé dans [`../docs/TODO.md`](../docs/TODO.md)
§6 ter : aucun déploiement (ni Docker Compose, ni Kubernetes), aucune
restauration de sauvegarde, aucun test de charge, aucun appel réel à un
fournisseur d'IA ou d'intégration, aucune réunion réelle transcrite, aucun
binaire Windows ni macOS.
