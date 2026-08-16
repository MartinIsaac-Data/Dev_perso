# Déploiement en production

Netlify héberge uniquement le **frontend** (fichiers statiques). Le
**backend** (serveur Express) et la **base PostgreSQL** doivent être
hébergés ailleurs. Configuration recommandée, gratuite pour démarrer :

| Composant | Service | Pourquoi |
| --- | --- | --- |
| Frontend | Netlify | Build Vite statique, `netlify.toml` déjà prêt dans `frontend/` |
| Backend | Render (Web Service, Docker) | Utilise `backend/Dockerfile` tel quel, migrations Prisma automatiques au démarrage |
| Base de données | Neon (PostgreSQL managé) | Connection string PostgreSQL standard, tier gratuit suffisant pour la démo |

L'ordre ci-dessous doit être respecté : la base avant le backend, le
backend avant le frontend (le frontend a besoin de l'URL du backend).

---

## 1. Base de données — Neon

1. Créer un compte sur [neon.tech](https://neon.tech), créer un projet.
2. Récupérer la **connection string** (format
   `postgresql://user:password@host/dbname?sslmode=require`).
   → Ce sera `DATABASE_URL` du backend.

Render Postgres ou tout autre PostgreSQL managé fonctionne aussi — Prisma
ne dépend pas d'un fournisseur particulier.

## 2. Backend — Render

1. [render.com](https://render.com) → **New +** → **Web Service** → connecter
   le dépôt `MartinIsaac-Data/Dev_perso`.
2. **Root Directory** : `pressing-app/backend`
3. **Runtime** : `Docker` (Render détecte `backend/Dockerfile` automatiquement).
4. **Health Check Path** : `/api/health`
5. Variables d'environnement :

   | Clé | Valeur |
   | --- | --- |
   | `DATABASE_URL` | connection string Neon de l'étape 1 |
   | `JWT_SECRET` | chaîne aléatoire longue (ex. générée avec `openssl rand -hex 32`) |
   | `JWT_EXPIRES_IN` | `8h` |
   | `PORT` | `4000` |
   | `CORS_ORIGIN` | l'URL Netlify (étape 3) — à mettre à jour une fois connue, voir étape 4 |

6. Déployer. Le `Dockerfile` exécute `prisma migrate deploy` puis démarre
   le serveur — le schéma est créé automatiquement, aucune étape manuelle.
7. Charger le jeu de données de démonstration une seule fois, depuis un
   poste local avec `DATABASE_URL` pointé vers Neon :
   ```bash
   cd pressing-app/backend
   DATABASE_URL="<connection string Neon>" npm run seed
   ```
8. Noter l'URL du service (ex. `https://pressing-backend.onrender.com`).

Le tier gratuit de Render met le service en veille après inactivité — le
premier appel après une pause prend ~30s (cold start). Passer sur un plan
payant supprime cette latence.

## 3. Frontend — Netlify

1. [app.netlify.com](https://app.netlify.com) → **Add new site** →
   **Import an existing project** → sélectionner le dépôt.
2. **Base directory** : `pressing-app/frontend`
   (Netlify utilisera alors `frontend/netlify.toml`, déjà commité, pour le
   build command / publish directory / réécriture SPA.)
3. Variable d'environnement à ajouter dans Netlify (Site settings → Environment
   variables) :

   | Clé | Valeur |
   | --- | --- |
   | `VITE_API_URL` | `https://pressing-backend.onrender.com/api` (URL Render de l'étape 2, suffixée `/api`) |

4. Déployer. Netlify donne une URL du type `https://<nom-du-site>.netlify.app`.

## 4. Reboucler CORS

Une fois l'URL Netlify connue, revenir sur Render et mettre à jour
`CORS_ORIGIN` avec cette URL exacte (sans slash final), puis redéployer le
backend. Sans cette étape, le navigateur bloquera les appels API depuis le
frontend en production (CORS).

`CORS_ORIGIN` accepte plusieurs origines séparées par des virgules
(`https://site.netlify.app,https://mondomaine.com`) si plusieurs frontends
doivent pouvoir appeler la même API.

## Alternative backend : Railway

Railway fonctionne aussi bien que Render pour ce backend (même Dockerfile) :
**New Project** → **Deploy from GitHub repo** → régler *Root Directory* sur
`pressing-app/backend` → ajouter un plugin PostgreSQL Railway (fournit
`DATABASE_URL` automatiquement) → ajouter les autres variables d'environnement
listées ci-dessus.

## Points d'attention

- **QR code du ticket** : le backend construit l'URL de suivi à partir de
  `CORS_ORIGIN` (`backend/src/controllers/orderController.ts`). Vérifier
  qu'elle correspond bien à l'URL Netlify finale pour que le QR code des
  tickets pointe au bon endroit une fois en production.
- **Secrets** : ne jamais committer `JWT_SECRET` ou `DATABASE_URL` — ils
  vivent uniquement dans les variables d'environnement Render/Netlify.
- **Migrations futures** : toute nouvelle migration Prisma (`prisma migrate dev`
  en local) est appliquée automatiquement en production au prochain déploiement
  Render (`prisma migrate deploy` fait partie du `CMD` du Dockerfile).
