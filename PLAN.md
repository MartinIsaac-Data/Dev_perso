# Plan — Application de Gestion de Pressing

## État des lieux (avant travail)

Le dépôt contient un projet existant, **Transformation OS** (racine du repo) :
Python/FastAPI, SQLite/Alembic, frontend Vite+React séparé, portfolio personnel
sans rapport avec un pressing. Stack, domaine et objectif n'ont rien en commun
avec la demande (Node.js/TS + PostgreSQL/Prisma pour un POS de pressing).

Décision : ne pas toucher à Transformation OS (racine : `backend/`, `frontend/`,
`ARCHITECTURE.md`, etc. existants restent intacts). La nouvelle application est
développée dans un nouveau workspace `pressing-app/` à la racine du dépôt, avec
son propre `backend/`, `frontend/`, `docker-compose.yml` et `README.md`.

## Stack retenue

- Backend : Node.js, TypeScript, Express, Prisma ORM, PostgreSQL, Zod, JWT, bcrypt
- Frontend : React, TypeScript, Vite, Tailwind CSS, composants style shadcn/ui
  (Radix primitives écrits localement), Recharts, Lucide icons
- Auth : JWT (access token) + RBAC par rôle (matrice de permissions en code)

## Simplifications assumées pour la v1 (documentées, pas cachées)

- `Role`/`Permission` : implémentés comme enum + matrice de permissions
  côté code (`backend/src/lib/permissions.ts`) plutôt que tables dynamiques.
  Suffisant pour un vrai RBAC appliqué ; migrable vers des tables plus tard.
- `Employee` : fusionné dans `User` (poste, date d'embauche) plutôt qu'une
  entité dupliquée — les stats de performance sont calculées par requête.
- SMS/WhatsApp/Email : `NotificationService` avec providers `LogProvider`
  (écrit en base + log) actif par défaut ; interfaces prêtes pour brancher
  Twilio / WhatsApp Business API / SMTP réels via variables d'environnement.
- Mobile Money (MTN/Orange) : moyen de paiement enregistré tel quel (traçable,
  soldes réellement mis à jour) ; pas d'appel réseau vers un agrégateur —
  aucune clé fournie.
- Photos d'articles : upload local (disque, `/uploads`) plutôt que S3.

## Phases (ordre d'exécution réel)

1. **Foundation** — monorepo, Prisma schema complet, migrations, auth JWT,
   RBAC middleware, layout React (sidebar/topbar/dark mode).
2. **Core** — Clients, Services, Commandes + Articles, Paiements, ticket
   (PDF + QR code), calcul de prix automatique.
3. **Operations** — statuts de commande, livraisons, caisse, dépenses, stock.
4. **Management** — dashboard KPIs + graphiques réels (issus de la DB),
   rapports, employés, multi-agences, audit log.
5. **Advanced** — recherche globale (Ctrl+K), suivi commande public,
   exports CSV/PDF, notifications (providers configurables).

Chaque phase est committée séparément. Seed réaliste (utilisateurs de démo,
clients, commandes, paiements) exécuté avant livraison finale pour que le
dashboard ne soit jamais vide.
