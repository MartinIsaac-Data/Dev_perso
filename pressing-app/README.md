# Pressing Étoile — Application de gestion de pressing

Application web complète (POS + back-office) pour la gestion d'un pressing :
clients, commandes, articles, services, tarification, paiements, caisse,
dépenses, stock, livraisons, employés, multi-agences, dashboard, rapports,
audit log et suivi de commande public.

Voir [`PLAN.md`](../PLAN.md) (à la racine du dépôt) pour l'état des lieux,
les décisions d'architecture et les phases de développement, et
[`DEPLOYMENT.md`](./DEPLOYMENT.md) pour déployer en production (Netlify +
Render + Neon).

## Stack

- **Backend** : Node.js, TypeScript, Express, Prisma ORM, PostgreSQL, Zod, JWT, bcrypt
- **Frontend** : React, TypeScript, Vite, Tailwind CSS, composants style shadcn/ui, Recharts, Lucide
- **Base de données** : PostgreSQL
- **Tests** : Vitest + Supertest (backend)

## Démarrage rapide (sans Docker)

Prérequis : Node.js 20+, PostgreSQL 14+ (local ou distant).

```bash
# 1. Cloner le dépôt puis se placer dans pressing-app/
cd pressing-app

# 2. Backend
cd backend
npm install
cp .env.example .env          # ajuster DATABASE_URL si besoin
npx prisma migrate dev        # crée le schéma en base
npm run seed                  # jeu de données de démonstration
npm run dev                   # API sur http://localhost:4000

# 3. Frontend (dans un second terminal)
cd ../frontend
npm install
cp .env.example .env          # VITE_API_URL=http://localhost:4000/api
npm run dev                   # interface sur http://localhost:5173
```

PostgreSQL doit être joignable à l'URL définie dans `backend/.env`
(`DATABASE_URL`). Exemple pour créer rapidement une base locale :

```bash
sudo -u postgres psql -c "CREATE USER pressing WITH PASSWORD 'pressing' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE pressing_db OWNER pressing;"
```

## Démarrage avec Docker

```bash
cd pressing-app
docker compose up --build
```

Cela lance PostgreSQL, le backend (migrations Prisma appliquées
automatiquement au démarrage) et le frontend servi par Nginx (qui proxifie
`/api` vers le backend). Pour charger le jeu de données de démonstration une
fois les conteneurs démarrés :

```bash
cd backend && npm run seed   # DATABASE_URL doit pointer vers localhost:5432
```

(le port Postgres du conteneur est publié sur l'hôte, donc `npm run seed`
lancé depuis `backend/` avec le `.env` par défaut fonctionne directement).

## Comptes de démonstration

Mot de passe pour tous : **`Demo1234!`**

| Rôle | Email |
| --- | --- |
| SUPER_ADMIN | superadmin@pressing.demo |
| ADMIN | admin@pressing.demo |
| MANAGER | manager@pressing.demo |
| CASHIER | cashier1@pressing.demo, cashier2@pressing.demo |
| OPERATOR | operator1@pressing.demo, operator2@pressing.demo, operator3@pressing.demo |
| DELIVERY | delivery1@pressing.demo, delivery2@pressing.demo |

Le seed crée 2 agences, 50 clients, ~110 commandes réparties sur les 60
derniers jours, des paiements, dépenses, mouvements de caisse et de stock —
le dashboard n'est jamais vide après installation.

## Tests

```bash
cd backend
npm run seed   # requis : les tests d'intégration se connectent avec le compte manager@pressing.demo
npm test
```

26 tests (unitaires : calcul de prix, de solde, de remise, transitions de
statut, calcul de caisse ; intégration : création de commande, paiement,
transitions de statut invalides/valides, création client, doublon de
téléphone).

## Build de production

```bash
cd backend && npm run build && npm start
cd frontend && npm run build && npm run preview
```

## Déploiement (Netlify + Render + Neon)

`frontend/netlify.toml` est prêt pour un déploiement Netlify (build command,
publish directory, réécriture SPA). Netlify n'héberge que le frontend
statique — le backend et PostgreSQL doivent être hébergés séparément.
Étapes détaillées, variables d'environnement et ordre de déploiement :
voir [`DEPLOYMENT.md`](./DEPLOYMENT.md).

## Fonctionnalités couvertes

- **Auth & RBAC** : JWT, 6 rôles (SUPER_ADMIN, ADMIN, MANAGER, CASHIER,
  OPERATOR, DELIVERY), permissions appliquées côté backend sur chaque route.
- **Clients** : CRUD, recherche, historique, statistiques.
- **Services & tarification** : catalogue configurable, prix standard/express.
- **Commandes** : création multi-articles, calcul automatique des prix et du
  solde, statuts avec machine à états (`RECEIVED → … → COMPLETED`), historique
  de statut, ticket imprimable avec QR code de suivi.
- **Paiements** : partiels/complets, mise à jour réelle du solde, plusieurs
  moyens de paiement (Mobile Money enregistré comme moyen de paiement — pas
  d'intégration réseau réelle, aucune clé API fournie).
- **Livraisons** : assignation livreur, suivi de statut, vue du jour.
- **Caisse** : ouverture/fermeture, encaissements/décaissements automatiques
  liés aux commandes et dépenses, écart de caisse.
- **Dépenses, stock** (entrées/sorties/ajustements, alertes seuil bas).
- **Dashboard & rapports** : KPIs et graphiques calculés depuis la base
  (aucune donnée mockée), filtres par période, export CSV.
- **Employés, multi-agences, audit log, paramètres, recherche globale
  (Ctrl+K), suivi de commande public** (`/track`, sans authentification).

## Ce qui nécessite une configuration externe pour la production

- **SMS / Email / WhatsApp** : `NotificationService` (backend) définit une
  interface `NotificationProvider` par canal. Sans variables d'environnement
  (`SMS_PROVIDER`, `EMAIL_PROVIDER`, `WHATSAPP_PROVIDER`), les notifications
  sont écrites en base (`Notification`) et loguées côté serveur, sans envoi
  réel — c'est le comportement par défaut. Brancher Twilio, une API SMTP ou
  l'API WhatsApp Business consiste à implémenter l'interface et renseigner
  les clés dans `backend/.env`.
- **Mobile Money (MTN/Orange)** : enregistré comme moyen de paiement, sans
  appel réseau vers un agrégateur (aucune clé fournie).
- **Photos d'articles** : le champ `photoUrl` accepte une URL ; aucun
  service d'upload/stockage n'est branché par défaut.
