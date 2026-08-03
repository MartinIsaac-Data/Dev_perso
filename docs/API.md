# MindFlow AI — Conception de l'API

> **Phase 0 — Conception.** Ce document spécifie le **contrat** de l'API : ressources,
> verbes, formats, conventions de nommage et taxonomie d'erreurs. Aucun code n'est
> écrit ; les exemples JSON décrivent des charges utiles, pas des implémentations.

| | |
| --- | --- |
| **Style** | REST orienté ressources, JSON, + SSE pour la progression |
| **Base** | `https://api.mindflow.ai/v1` |
| **Spécification** | OpenAPI 3.1, générée depuis les schémas, publiée à chaque version |
| **Authentification** | Bearer JWT (OAuth 2.1) |

---

## Table des matières

1. [Principes de conception](#1-principes-de-conception)
2. [Conventions de nommage](#2-conventions-de-nommage)
3. [Conventions transverses](#3-conventions-transverses)
4. [Authentification et autorisation](#4-authentification-et-autorisation)
5. [Catalogue des ressources](#5-catalogue-des-ressources)
6. [Gestion des erreurs](#6-gestion-des-erreurs)
7. [Pagination, filtrage, tri](#7-pagination-filtrage-tri)
8. [Idempotence et concurrence](#8-idempotence-et-concurrence)
9. [Synchronisation client](#9-synchronisation-client)
10. [Temps réel — SSE](#10-temps-réel--sse)
11. [Quotas et limitation de débit](#11-quotas-et-limitation-de-débit)
12. [Versionnage et dépréciation](#12-versionnage-et-dépréciation)
13. [Webhooks sortants](#13-webhooks-sortants)

---

## 1. Principes de conception

| # | Principe | Conséquence concrète |
| --- | --- | --- |
| A1 | **Les ressources sont des noms, les états sont des transitions** | `POST /captures/{id}/complete`, pas `POST /completeCapture` |
| A2 | **Rien de coûteux n'est synchrone** | Aucun endpoint n'appelle un LLM ou un STT dans le cycle requête/réponse (exception documentée : `/search` en mode `answer`) |
| A3 | **Toute écriture est idempotente** | `Idempotency-Key` sur les `POST`, `If-Match` sur les `PATCH` |
| A4 | **Le client peut toujours rejouer** | Une requête perdue se rejoue sans créer de doublon |
| A5 | **Les erreurs sont des données** | RFC 9457, code applicatif stable, action possible indiquée |
| A6 | **Aucun champ n'est retiré sans dépréciation** | Cycle de dépréciation de 6 mois documenté |
| A7 | **La réponse ne dépend jamais d'un identifiant deviné** | Toute ressource est vérifiée en autorisation, puis en RLS |
| A8 | **La pagination est par curseur** | Un décalage (`offset`) est instable sur un flux qui grandit |

---

## 2. Conventions de nommage

### 2.1 URI

| Règle | Exemple correct | Exemple incorrect |
| --- | --- | --- |
| Nom de collection au pluriel, `kebab-case` | `/entries`, `/share-links` | `/entry`, `/shareLinks` |
| Identifiant en segment de chemin | `/entries/{entry_id}` | `/entries?id=…` |
| Sous-ressource imbriquée à un seul niveau | `/captures/{id}/transcript` | `/accounts/{a}/users/{u}/captures/{c}/transcript` |
| Action non CRUD en sous-ressource verbale | `/captures/{id}/complete` | `/completeCapture` |
| Paramètre de requête en `snake_case` | `?entry_type=task&updated_since=…` | `?entryType=…` |
| Pas d'extension de format | `/entries` | `/entries.json` |
| Pas de verbe dans un nom de collection | `/exports` | `/getExports` |

### 2.2 Corps JSON

| Règle | Détail |
| --- | --- |
| Clés en `snake_case` | Cohérent avec la base et Python ; le client Dart fait la conversion |
| Horodatages en ISO 8601 UTC avec `Z` | `2026-06-09T11:47:03.221Z` |
| Durées en millisecondes, suffixe `_ms` | `duration_ms: 14320` |
| Montants en centimes, suffixe `_cents` | `price_cents: 900` |
| Énumérations en `snake_case` minuscule | `"entry_type": "task"` |
| Identifiants : UUID canonique en chaîne | `"018f2c1e-…"` |
| Booléens : `is_`, `has_`, `include_` | `is_current`, `include_audio` |
| Champ absent ≠ champ `null` | L'absence signifie « non modifié » en `PATCH` ; `null` signifie « effacer » |
| Collections toujours sous `data` | `{ "data": [...], "page": {...} }` |
| Jamais de tableau à la racine | Empêche l'ajout ultérieur de métadonnées |

### 2.3 Nommage des événements et des codes

| Élément | Forme | Exemple |
| --- | --- | --- |
| Événement SSE / webhook | `<domaine>.<objet>.<action au passé>` | `capture.transcription.completed` |
| Code d'erreur applicatif | `snake_case`, sans préfixe HTTP | `entry_version_conflict` |
| Type d'erreur (URI) | `https://api.mindflow.ai/errors/<code>` | `…/errors/quota_exceeded` |
| Périmètre de jeton | `<ressource>:<action>` | `captures:create`, `entries:read` |
| Nom de métrique | `<domaine>_<mesure>_<unité>` | `capture_time_to_publish_seconds` |

### 2.4 En-têtes personnalisés

| En-tête | Sens | Direction |
| --- | --- | --- |
| `Idempotency-Key` | Clé d'idempotence fournie par le client | → |
| `X-Request-Id` | Identifiant de corrélation | ↔ |
| `X-Client-Version` | Version applicative du client | → |
| `X-Client-Platform` | `ios`, `android`, `web` | → |
| `X-RateLimit-Limit` / `-Remaining` / `-Reset` | État du quota de débit | ← |
| `X-Quota-Remaining` | Quota de plan restant sur la métrique concernée | ← |
| `Deprecation` / `Sunset` | Dépréciation d'un endpoint (RFC 8594) | ← |

---

## 3. Conventions transverses

### 3.1 Codes de statut utilisés

| Code | Usage précis |
| --- | --- |
| `200` | Lecture réussie, ou écriture dont le résultat est immédiat |
| `201` | Ressource créée — l'en-tête `Location` la désigne |
| `202` | Accepté, traitement asynchrone en cours |
| `204` | Suppression réussie, aucun corps |
| `304` | `If-None-Match` satisfait |
| `400` | Requête malformée ou état incompatible |
| `401` | Authentification absente, invalide ou expirée |
| `402` | Quota de plan dépassé — action possible : upgrade |
| `403` | Authentifié mais non autorisé sur cette ressource |
| `404` | Inexistante **ou hors du périmètre du locataire** (indistinguable, volontairement) |
| `409` | Conflit de version ou doublon |
| `410` | Ressource définitivement supprimée |
| `413` | Corps trop volumineux |
| `422` | Validation sémantique échouée (champ présent mais invalide) |
| `429` | Limite de débit atteinte |
| `500` | Erreur interne non attendue |
| `502` / `503` | Dépendance amont indisponible |

**Note sur le 404 vs 403** : une ressource appartenant à un autre locataire retourne
`404`, jamais `403`. Un `403` confirmerait son existence.

### 3.2 Enveloppe des réponses

Ressource unique :

```json
{
  "data": {
    "id": "018f2c1e-4a2b-7c3d-9e1f-a5b6c7d8e9f0",
    "object": "entry",
    "...": "..."
  }
}
```

Collection :

```json
{
  "data": [ { "object": "entry", "...": "..." } ],
  "page": {
    "next_cursor": "eyJ0IjoiMjAyNi0wNi0wOVQxMTo0NyJ9",
    "has_more": true,
    "limit": 50
  }
}
```

Chaque objet porte un champ `object` indiquant son type. Cela permet aux clients de
traiter des collections hétérogènes (résultats de recherche) sans inférence.

### 3.3 Négociation et compression

- `Content-Type: application/json; charset=utf-8`
- Compression `gzip` et `br` (Brotli) supportées.
- `ETag` sur les ressources individuelles ; `If-None-Match` honoré.
- Les corps de requête sont plafonnés à 1 Mio (l'audio passe par URL présignée,
  jamais par le corps d'une requête API).

---

## 4. Authentification et autorisation

### 4.1 Flux

```
POST /v1/auth/magic-link         → e-mail envoyé
GET  /v1/auth/magic-link/verify  → jeton d'accès + rafraîchissement
POST /v1/auth/token/refresh      → rotation du jeton de rafraîchissement
POST /v1/auth/token/revoke       → révocation
POST /v1/auth/oauth/{provider}   → Apple / Google (OIDC)
POST /v1/auth/device-token       → jeton restreint pour widget / montre
```

### 4.2 Structure du jeton d'accès

| Revendication | Contenu |
| --- | --- |
| `sub` | `user_id` |
| `act` | `account_id` |
| `scp` | Liste de périmètres |
| `pln` | Code de plan (permet de refuser tôt un appel hors plan) |
| `dev` | `device_id` |
| `exp` | 15 minutes |
| `jti` | Identifiant, pour la révocation |

### 4.3 Périmètres

| Périmètre | Accorde |
| --- | --- |
| `captures:create` | Créer une capture (seul périmètre des jetons d'appareil) |
| `captures:read` | Lire captures et transcriptions |
| `captures:delete` | Supprimer |
| `entries:read` / `entries:write` | Lecture / écriture des entrées |
| `search:query` | Recherche lexicale et sémantique |
| `search:answer` | Réponse générée (RAG) — coûteux, séparé volontairement |
| `integrations:manage` | Connecteurs |
| `billing:manage` | Abonnement |
| `account:delete` | Suppression de compte — exige une réauthentification récente |

### 4.4 Réauthentification pour les actions sensibles

Les actions suivantes exigent que le jeton ait été émis il y a moins de 5 minutes
(sinon `401` avec `code: reauthentication_required`) :

- Suppression de compte
- Changement d'e-mail
- Génération d'une clé d'API
- Export incluant l'audio

---

## 5. Catalogue des ressources

### 5.1 Vue d'ensemble

| Ressource | Endpoints principaux |
| --- | --- |
| `captures` | `POST /captures`, `POST /captures/{id}/complete`, `GET`, `DELETE`, `POST /{id}/reprocess` |
| `transcripts` | `GET /captures/{id}/transcript` |
| `entries` | `GET`, `POST`, `PATCH`, `DELETE`, `POST /{id}/transform`, `POST /{id}/complete` |
| `projects` | CRUD complet |
| `tags` | `GET`, `PATCH`, `DELETE` |
| `links` | `POST /entries/{id}/links`, `DELETE /links/{id}` |
| `search` | `POST /search` |
| `meetings` | `GET /meetings/{id}`, `POST /meetings/{id}/regenerate` |
| `reviews` | `GET /reviews/daily`, `GET /reviews/weekly` |
| `reminders` | CRUD |
| `share-links` | `POST`, `GET`, `DELETE` ; `GET /public/shares/{token}` |
| `exports` | `POST /exports`, `GET /exports/{id}` |
| `integrations` | `GET`, `POST`, `DELETE`, `POST /{id}/sync` |
| `billing` | `GET /billing/subscription`, `GET /billing/usage`, `POST /billing/portal` |
| `me` | `GET`, `PATCH`, `DELETE` |
| `sync` | `GET /sync/changes` |
| `events` | `GET /events/stream` (SSE) |

---

### 5.2 Captures

#### `POST /v1/captures` — déclarer une capture

Crée l'enregistrement et retourne une URL d'upload présignée. **N'accepte pas
l'audio dans son corps.**

```json
// Requête
{
  "client_capture_id": "018f2c1e-4a2b-7c3d-9e1f-a5b6c7d8e9f0",
  "kind": "quick",
  "duration_ms": 14320,
  "audio_format": "m4a",
  "audio_bytes": 143200,
  "audio_sample_rate": 16000,
  "captured_at": "2026-06-09T11:47:03.221Z",
  "capture_timezone": "Europe/Paris",
  "source": "widget",
  "language_hint": "fr"
}
```

```json
// 201 Created
{
  "data": {
    "object": "capture",
    "id": "018f2c1e-4a2b-7c3d-9e1f-a5b6c7d8e9f0",
    "status": "pending_upload",
    "duration_ms": 14320,
    "captured_at": "2026-06-09T11:47:03.221Z",
    "upload": {
      "url": "https://storage.mindflow.ai/…",
      "method": "PUT",
      "headers": { "content-type": "audio/mp4" },
      "expires_at": "2026-06-09T11:52:03Z"
    },
    "created_at": "2026-06-09T11:47:04.010Z"
  }
}
```

**Comportements notables**

| Situation | Réponse |
| --- | --- |
| `client_capture_id` déjà connu | `200` avec la capture existante — pas de doublon |
| Durée > limite du plan | `422`, `code: capture_too_long` |
| Quota mensuel dépassé | `201` avec `processing_mode: "degraded"` — **la capture est acceptée**, seul l'enrichissement IA est différé |

Ce dernier point est structurant : le principe P2 du PRD (« la capture ne doit jamais
échouer ») prime sur la contrainte commerciale.

#### `POST /v1/captures/{id}/complete`

Signale la fin de l'upload et déclenche le pipeline. Réponse `202`.

#### `GET /v1/captures/{id}`

```json
{
  "data": {
    "object": "capture",
    "id": "018f2c1e-…",
    "status": "completed",
    "kind": "quick",
    "duration_ms": 14320,
    "captured_at": "2026-06-09T11:47:03.221Z",
    "source": "widget",
    "audio": {
      "available": true,
      "url": "https://storage.mindflow.ai/…",
      "expires_at": "2026-06-09T12:47:00Z"
    },
    "transcript": {
      "id": "018f2c1f-…",
      "language": "fr",
      "confidence": 0.94,
      "text": "Faut que je rappelle le DAF de Vinci jeudi pour le budget Q3…",
      "word_count": 24
    },
    "entries": [
      { "id": "018f2c20-…", "entry_type": "task", "title": "Rappeler le DAF de Vinci" },
      { "id": "018f2c21-…", "entry_type": "task", "title": "Relire la clause RGPD" }
    ],
    "processing": {
      "started_at": "2026-06-09T11:47:05Z",
      "finished_at": "2026-06-09T11:47:16Z",
      "duration_ms": 11842
    }
  }
}
```

#### `DELETE /v1/captures/{id}`

| Paramètre | Effet |
| --- | --- |
| `?cascade=false` (défaut) | Supprime l'audio et la transcription ; **les entrées dérivées survivent** |
| `?cascade=true` | Supprime aussi les entrées issues de cette capture |
| `?audio_only=true` | Ne supprime que l'audio, conserve la transcription |

Réponse `204`. La suppression est logique ; la purge physique intervient sous 24 h.

---

### 5.3 Entrées

#### `GET /v1/entries`

| Paramètre | Type | Défaut |
| --- | --- | --- |
| `entry_type` | Liste séparée par des virgules | tous |
| `status` | Liste | `active,needs_review` |
| `project_id` | UUID | — |
| `tag` | Libellé normalisé | — |
| `occurred_from` / `occurred_to` | Date ISO | — |
| `due_before` | Date ISO — tâches uniquement | — |
| `q` | Recherche lexicale rapide | — |
| `sort` | `occurred_at`, `-occurred_at`, `due_at`, `-created_at` | `-occurred_at` |
| `cursor`, `limit` | Pagination | `limit=50`, max `200` |

#### `PATCH /v1/entries/{id}`

Mise à jour partielle avec verrouillage optimiste.

```
If-Match: "3"
```

```json
{
  "entry_type": "task",
  "project_id": "018f2c30-…",
  "task": { "due_at": "2026-06-12T09:00:00Z", "due_precision": "hour" }
}
```

| Réponse | Sens |
| --- | --- |
| `200` | Mis à jour, `version` incrémentée |
| `409` | `If-Match` obsolète — le corps contient l'état serveur pour permettre une fusion côté client |
| `422` | Transition invalide (ex. passer `meeting` → `task`) |

**Effet de bord documenté** : tout `PATCH` modifiant `entry_type`, `due_at` ou
`project_id` sur une entrée d'origine `ai` crée un `correction_event`, qui alimente
l'évaluation hors ligne du modèle. Ce comportement est visible dans la politique de
confidentialité et désactivable via le consentement `model_evaluation`.

#### `POST /v1/entries/{id}/transform`

```json
{ "target_type": "task", "keep_original": false }
```

Transforme une entrée d'un type vers un autre en conservant la source et en créant un
lien `derived_from`. Les attributs incompatibles sont conservés dans `body` plutôt que
perdus.

#### `POST /v1/entries/{id}/complete` — `POST /v1/entries/{id}/snooze`

Transitions d'état des tâches. `snooze` accepte `{"until": "2026-06-15T08:00:00Z"}`
ou `{"preset": "tomorrow_morning"}`.

---

### 5.4 Recherche

#### `POST /v1/search`

`POST` et non `GET` : la requête est du contenu utilisateur, elle ne doit pas se
retrouver dans les journaux d'accès, l'historique du navigateur ou les référents.

```json
// Requête
{
  "query": "qu'est-ce que j'ai dit sur la refonte du site ?",
  "mode": "answer",
  "filters": {
    "entry_types": ["idea", "decision", "task"],
    "project_id": null,
    "occurred_from": "2026-01-01T00:00:00Z"
  },
  "limit": 20
}
```

| `mode` | Comportement | Périmètre requis | Coût |
| --- | --- | --- | --- |
| `lexical` | Plein texte seul | `search:query` | Nul |
| `semantic` | Hybride lexical + vectoriel, résultats bruts | `search:query` | Faible |
| `answer` | Hybride + synthèse générée avec citations | `search:answer` | Élevé — décompté du quota |

```json
// 200 OK — mode "answer"
{
  "data": {
    "object": "search_result",
    "answer": {
      "text": "Vous en avez parlé trois fois. Le 12 mars vous envisagiez une refonte complète [1]. Le 2 avril vous avez arbitré pour une refonte progressive par pages, avec un budget de 15 k€ [2]. Le 18 mai vous notiez que le prestataire n'avait pas répondu [3].",
      "citations": [
        { "marker": 1, "entry_id": "018f2c40-…", "chunk_id": "018f2c41-…", "occurred_at": "2026-03-12T09:14:00Z" },
        { "marker": 2, "entry_id": "018f2c42-…", "chunk_id": "018f2c43-…", "occurred_at": "2026-04-02T17:31:00Z" },
        { "marker": 3, "entry_id": "018f2c44-…", "chunk_id": "018f2c45-…", "occurred_at": "2026-05-18T08:02:00Z" }
      ],
      "model": "claude-opus-5",
      "generated_at": "2026-06-09T14:22:11Z"
    },
    "results": [
      {
        "object": "search_hit",
        "entry": { "id": "018f2c42-…", "entry_type": "decision", "title": "Refonte progressive du site" },
        "excerpt": "…on part sur une refonte page par page, budget 15 000 euros…",
        "score": 0.0312,
        "matched_by": ["semantic", "lexical"]
      }
    ]
  },
  "page": { "has_more": false, "limit": 20 }
}
```

**Garanties du mode `answer`**

| Garantie | Mise en œuvre |
| --- | --- |
| Toute affirmation est citée | Schéma de sortie imposant les marqueurs ; réponse rejetée sinon |
| Aucune citation inventée | Vérification programmatique : chaque `chunk_id` cité doit figurer dans le contexte fourni |
| Absence de résultat assumée | Si le contexte est insuffisant, `answer` vaut `null` et `suggestions` est peuplé — jamais de réponse fabriquée |
| Latence bornée | Délai d'attente de 12 s ; au-delà, dégradation vers `semantic` et `answer: null` |

C'est l'unique endpoint appelant un LLM de manière synchrone. Le compromis est
documenté dans `Decisions.md` ADR-025.

---

### 5.5 Synchronisation

#### `GET /v1/sync/changes`

```
GET /v1/sync/changes?since=2026-06-09T11:00:00Z&limit=500
```

```json
{
  "data": {
    "object": "sync_delta",
    "entries":  { "upserted": [ … ], "deleted": ["018f2c50-…"] },
    "captures": { "upserted": [ … ], "deleted": [] },
    "projects": { "upserted": [ … ], "deleted": [] },
    "tags":     { "upserted": [ … ], "deleted": [] }
  },
  "page": {
    "next_cursor": "2026-06-09T11:47:16.221Z|018f2c21-…",
    "has_more": false
  }
}
```

| Aspect | Règle |
| --- | --- |
| Curseur | `updated_at|id` — l'identifiant départage les horodatages identiques |
| Suppressions | Marqueurs conservés 90 jours ; au-delà, une resynchronisation complète est demandée |
| Curseur trop ancien | `410 Gone`, `code: sync_cursor_expired` → le client refait un `full_sync` |
| Ordre | Croissant sur `updated_at`, stable |

---

### 5.6 Facturation

#### `GET /v1/billing/usage`

```json
{
  "data": {
    "object": "usage",
    "period": { "start": "2026-06-01", "end": "2026-06-30" },
    "plan": "free",
    "metrics": [
      { "metric": "quick_captures",   "used": 47,  "limit": 60,  "remaining": 13 },
      { "metric": "meeting_minutes",  "used": 22,  "limit": 30,  "remaining": 8 },
      { "metric": "semantic_queries", "used": 10,  "limit": 10,  "remaining": 0 }
    ]
  }
}
```

Cet endpoint est appelé par le client pour afficher les compteurs, et sa réponse est
mise en cache 60 secondes côté client.

---

## 6. Gestion des erreurs

### 6.1 Format — RFC 9457 `application/problem+json`

```json
{
  "type": "https://api.mindflow.ai/errors/entry_version_conflict",
  "title": "La ressource a été modifiée ailleurs",
  "status": 409,
  "detail": "La version fournie (3) ne correspond pas à la version courante (5).",
  "instance": "/v1/entries/018f2c20-4a2b-7c3d-9e1f-a5b6c7d8e9f0",
  "code": "entry_version_conflict",
  "request_id": "req_01J8XKQ2M9",
  "current_version": 5,
  "current_state": { "entry_type": "task", "updated_at": "2026-06-09T19:32:00Z" }
}
```

Erreur de validation :

```json
{
  "type": "https://api.mindflow.ai/errors/validation_failed",
  "title": "Requête invalide",
  "status": 422,
  "code": "validation_failed",
  "request_id": "req_01J8XKQ2M9",
  "errors": [
    { "field": "duration_ms",  "code": "out_of_range", "detail": "Doit être compris entre 1 et 600000." },
    { "field": "audio_format", "code": "not_allowed",  "detail": "Valeurs acceptées : m4a, opus, wav, mp3." }
  ]
}
```

### 6.2 Catalogue des codes d'erreur

#### Authentification et autorisation

| Code | HTTP | Sens | Action client |
| --- | --- | --- | --- |
| `unauthenticated` | 401 | Jeton absent ou illisible | Reconnexion |
| `token_expired` | 401 | Jeton d'accès expiré | Rafraîchir |
| `token_revoked` | 401 | Jeton révoqué (rejeu détecté) | Reconnexion, **conserver la file locale** |
| `reauthentication_required` | 401 | Action sensible, jeton trop ancien | Redemander l'authentification |
| `insufficient_scope` | 403 | Périmètre manquant | Erreur de conception cliente |
| `account_suspended` | 403 | Compte suspendu | Afficher le motif |

#### Ressources

| Code | HTTP | Sens |
| --- | --- | --- |
| `resource_not_found` | 404 | Inexistante ou hors périmètre |
| `resource_deleted` | 410 | Supprimée définitivement |
| `entry_version_conflict` | 409 | Verrouillage optimiste |
| `duplicate_resource` | 409 | Contrainte d'unicité |
| `invalid_state_transition` | 400 | Transition d'état interdite |
| `validation_failed` | 422 | Champ invalide |

#### Captures

| Code | HTTP | Sens |
| --- | --- | --- |
| `capture_too_long` | 422 | Durée supérieure à la limite du plan |
| `capture_upload_expired` | 400 | URL présignée expirée — en redemander une |
| `capture_already_completed` | 409 | `complete` appelé deux fois |
| `capture_audio_unavailable` | 404 | Audio purgé par rétention |
| `unsupported_audio_format` | 422 | Format non pris en charge |

#### Quotas et débit

| Code | HTTP | Sens | Corps additionnel |
| --- | --- | --- | --- |
| `quota_exceeded` | 402 | Limite du plan atteinte | `metric`, `used`, `limit`, `resets_at`, `upgrade_url` |
| `rate_limited` | 429 | Trop de requêtes | `retry_after` |
| `payload_too_large` | 413 | Corps trop volumineux | `max_bytes` |

#### Amont et traitement

| Code | HTTP | Sens | Conséquence produit |
| --- | --- | --- | --- |
| `transcription_unavailable` | 503 | STT et repli indisponibles | Capture en file, retraitement automatique |
| `extraction_unavailable` | 503 | LLM indisponible | Entrée en `partially_processed` |
| `content_not_processed` | 200 | Le modèle a refusé de traiter le contenu | Message neutre ; **audio et transcription conservés** |
| `search_timeout` | 200 | Génération trop longue | Résultats bruts retournés, `answer: null` |
| `integration_unavailable` | 502 | Service tiers en échec | Connecteur mis en pause |

#### Système

| Code | HTTP | Sens |
| --- | --- | --- |
| `internal_error` | 500 | Bug — tracé, jamais détaillé au client |
| `service_unavailable` | 503 | Maintenance ou dépendance critique |
| `sync_cursor_expired` | 410 | Curseur trop ancien |
| `client_version_unsupported` | 400 | Version cliente trop ancienne |

### 6.3 Principes de traitement

| Principe | Détail |
| --- | --- |
| **Le code applicatif est le contrat, pas le code HTTP** | Plusieurs erreurs partagent un code HTTP ; le client se branche sur `code` |
| **Jamais de détail technique** | Ni trace d'appel, ni requête SQL, ni nom de table |
| **`request_id` systématique** | Permet à l'utilisateur de signaler et à l'équipe de retrouver |
| **Une erreur indique une action** | Chaque code du catalogue a une conduite à tenir documentée |
| **Les erreurs sont énumérées dans OpenAPI** | Le client peut générer une gestion exhaustive |
| **Le 402 n'interrompt jamais une capture** | Voir §5.2 |

### 6.4 Politique de reprise côté client

| Code HTTP | Reprise | Stratégie |
| --- | --- | --- |
| `408`, `429`, `500`, `502`, `503`, `504` | Oui | Backoff exponentiel `2^n` s, plafond 300 s, jitter ±20 %, max 8 tentatives |
| `409` | Oui, une fois | Relire, fusionner, réémettre |
| `4xx` autres | Non | Corriger la requête ou remonter à l'utilisateur |

Toute requête reprise porte le même `Idempotency-Key`.

---

## 7. Pagination, filtrage, tri

### 7.1 Pagination par curseur

```
GET /v1/entries?limit=50&cursor=eyJ0IjoiMjAyNi0wNi0wOVQxMTo0NyIsImkiOiIwMThmMmMyMSJ9
```

Le curseur est un objet encodé en base64url contenant la clé de tri et l'identifiant.
Il est **opaque** : le client ne doit jamais le construire ni l'interpréter.

| Règle | Détail |
| --- | --- |
| `limit` par défaut 50, maximum 200 | Un `limit` supérieur retourne `422` |
| Absence de `next_cursor` = fin | `has_more: false` est redondant mais explicite |
| Pas de nombre total | Compter coûte cher et n'apporte rien à l'usage |
| Un curseur reste valide 24 h | Au-delà : `410`, `code: cursor_expired` |

### 7.2 Filtrage

| Forme | Exemple |
| --- | --- |
| Égalité | `?status=active` |
| Liste (OU) | `?entry_type=task,idea` |
| Plage | `?occurred_from=…&occurred_to=…` |
| Négation | `?status_not=archived` |
| Présence | `?has_due_date=true` |

Le filtrage est **explicite et énuméré** : aucun langage de requête générique, qui
ouvrirait la porte à des requêtes coûteuses ou à des fuites par canal auxiliaire.

### 7.3 Tri

`?sort=-occurred_at` — le préfixe `-` inverse l'ordre. Un seul critère à la fois ;
l'identifiant sert toujours de départage implicite pour garantir la stabilité.

---

## 8. Idempotence et concurrence

### 8.1 Idempotence des créations

| Ressource | Clé d'idempotence |
| --- | --- |
| `captures` | `client_capture_id` dans le corps — **natif, obligatoire** |
| Autres `POST` | En-tête `Idempotency-Key` (UUID généré par le client) |

Comportement : la première requête est traitée et sa réponse mémorisée 24 h. Une
requête portant la même clé retourne la réponse mémorisée sans réexécuter l'effet.
Une même clé avec un corps différent retourne `409`, `code: idempotency_key_reuse`.

### 8.2 Concurrence sur les mises à jour

Verrouillage optimiste par `version`, exposé en `ETag` :

```
GET  /v1/entries/018f2c20-…        →  ETag: "3"
PATCH /v1/entries/018f2c20-…       →  If-Match: "3"
```

| Situation | Réponse |
| --- | --- |
| `If-Match` correspond | `200`, `version` → 4 |
| `If-Match` obsolète | `409` + état serveur complet pour permettre une fusion |
| `If-Match` absent | `428 Precondition Required` sur les ressources synchronisées |

Le corps du `409` contient l'état serveur : le client peut ainsi fusionner au niveau
du champ (voir `Architecture.md` §6.5) plutôt que d'imposer un choix binaire à
l'utilisateur.

---

## 9. Synchronisation client

### 9.1 Modèle

```
Premier lancement    → GET /sync/changes?since=1970-01-01  (paginé)
Retour au premier plan → GET /sync/changes?since=<curseur local>
Modification locale  → file sortante → PATCH avec If-Match
Notification push    → réveil → sync delta
```

### 9.2 Résolution de conflit

| Cas | Résolution |
| --- | --- |
| Champs disjoints modifiés | Fusion automatique, aucune interaction |
| Même champ, valeurs différentes | Dernière écriture gagnante par horodatage de modification |
| Entrée supprimée côté serveur, modifiée côté client | La suppression gagne ; l'entrée locale est conservée en « restaurable » 7 jours |
| Entrée modifiée par l'IA, éditée par l'utilisateur | **L'édition utilisateur gagne toujours** (`edited_by_user_at` fait autorité) |

Cette dernière règle est centrale : un retraitement automatique ne doit jamais
écraser une correction humaine.

---

## 10. Temps réel — SSE

### 10.1 `GET /v1/events/stream`

Flux d'événements serveur pour l'application au premier plan. Choisi plutôt que
WebSocket : le flux est unidirectionnel, SSE se reconnecte tout seul et traverse
proxys et pare-feu sans configuration.

```
event: capture.transcription.completed
id: 018f2c60-…
data: {"capture_id":"018f2c1e-…","language":"fr","confidence":0.94,
       "text_preview":"Faut que je rappelle le DAF de Vinci…"}

event: capture.completed
id: 018f2c61-…
data: {"capture_id":"018f2c1e-…","entry_ids":["018f2c20-…","018f2c21-…"],
       "needs_review":false}

: heartbeat
```

### 10.2 Catalogue d'événements

| Événement | Charge utile |
| --- | --- |
| `capture.uploaded` | `capture_id` |
| `capture.transcription.completed` | `capture_id`, `language`, `confidence`, `text_preview` |
| `capture.completed` | `capture_id`, `entry_ids`, `needs_review` |
| `capture.failed` | `capture_id`, `stage`, `code`, `recoverable` |
| `entry.updated` | `entry_id`, `version` |
| `meeting.ready` | `entry_id`, `action_count`, `decision_count` |
| `quota.warning` | `metric`, `remaining`, `resets_at` |
| `sync.required` | `reason` — invite le client à faire un delta |

### 10.3 Reprise

L'en-tête `Last-Event-ID` est honoré : à la reconnexion, les événements manqués sont
rejoués depuis un tampon de 5 minutes. Au-delà, un `sync.required` est émis et le
client fait un delta complet. **Le SSE n'est jamais la seule voie** : chaque événement
important a un équivalent en push et en delta de synchronisation.

---

## 11. Quotas et limitation de débit

### 11.1 Deux mécanismes distincts

| Mécanisme | Protège | Réponse |
| --- | --- | --- |
| **Limitation de débit** | L'infrastructure | `429` |
| **Quota de plan** | Le modèle économique | `402` |

### 11.2 Limites de débit

| Périmètre | Limite | Fenêtre |
| --- | --- | --- |
| Par utilisateur, global | 300 requêtes | 1 min |
| `POST /captures` | 30 | 1 min |
| `POST /search` mode `answer` | 10 | 1 min |
| `POST /auth/*` | 10 | 15 min |
| Par IP, non authentifié | 60 | 1 min |

Algorithme : fenêtre glissante par compteur Redis. En-têtes `X-RateLimit-*` renvoyés
sur toutes les réponses.

### 11.3 Quotas de plan

Vérifiés en début de requête à partir de `usage_counter`. Un avertissement
(`quota.warning`) est émis à 80 % de consommation.

**Exception fondamentale** : `POST /captures` n'est jamais refusé pour dépassement de
quota. La capture est acceptée, marquée `processing_mode: degraded`, et l'utilisateur
est informé sans être bloqué.

---

## 12. Versionnage et dépréciation

### 12.1 Stratégie

| Élément | Règle |
| --- | --- |
| Version majeure dans l'URI | `/v1/`, `/v2/` — uniquement pour une rupture inévitable |
| Ajouts | Toujours rétrocompatibles, sans nouvelle version |
| Version du client | En-tête `X-Client-Version` ; un client trop ancien reçoit `400 client_version_unsupported` |
| Version minimale supportée | Publiée dans `GET /v1/meta` |

### 12.2 Ce qui est une rupture

| Rupture | Non-rupture |
| --- | --- |
| Supprimer un champ de réponse | Ajouter un champ de réponse |
| Ajouter un champ requis en requête | Ajouter un champ optionnel en requête |
| Changer le type d'un champ | Ajouter une valeur d'énumération **en sortie** |
| Restreindre une énumération **en entrée** | Assouplir une validation |
| Changer un code HTTP existant | Ajouter un nouveau code d'erreur applicatif |
| Changer la sémantique d'un champ | Renforcer une garantie existante |

> ⚠️ Ajouter une valeur d'énumération en sortie n'est pas une rupture **à condition
> que les clients soient tolérants**. La règle est explicite dans le guide client :
> toute valeur d'énumération inconnue doit être traitée comme `unknown` et affichée
> de manière neutre, jamais provoquer un plantage.

### 12.3 Cycle de dépréciation

```
T+0    Annonce, en-tête Deprecation, documentation mise à jour
T+3m   Avertissement dans les réponses, alerte aux clients concernés
T+6m   Suppression — Sunset atteint
```

Un endpoint utilisé par plus de 1 % des clients actifs ne peut pas être supprimé sans
migration assistée.

---

## 13. Webhooks sortants

*Palier Business, v2.0.*

### 13.1 Contrat

```
POST https://client.example.com/webhook
Content-Type: application/json
X-MindFlow-Event: entry.created
X-MindFlow-Delivery: 018f2c70-…
X-MindFlow-Signature: t=1749473223,v1=5257a869e7…
```

```json
{
  "id": "018f2c70-…",
  "event": "entry.created",
  "created_at": "2026-06-09T11:47:16Z",
  "data": { "entry_id": "018f2c20-…", "entry_type": "task" }
}
```

### 13.2 Règles

| Règle | Détail |
| --- | --- |
| Charge utile mince | Identifiants uniquement — le contenu se récupère par l'API, sous authentification |
| Signature HMAC-SHA256 | Avec horodatage, fenêtre de tolérance de 5 min, résistant au rejeu |
| Reprise | 5 tentatives : 1 min, 5 min, 30 min, 2 h, 6 h |
| Désactivation | 20 échecs consécutifs → endpoint désactivé + notification |
| Ordre non garanti | Le consommateur doit être idempotent et se fier à `created_at` |
| HTTPS obligatoire | Aucune redirection suivie ; adresses IP privées refusées |

---

## Références

- Architecture et flux → `Architecture.md`
- Modèle de données → `Database.md`
- Architecture IA (mode `answer`) → `AI.md`
- Décisions et arbitrages → `Decisions.md`


---

## 14. Surface ajoutée en phase 2

### 14.1 Planification

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/v1/agenda` | Échéances d'une fenêtre. `view=day\|week\|month`, `anchor`, `include_done`, `include_unscheduled`, `project_id`. Les retards reviennent dans leur propre tableau |
| GET | `/v1/calendar` | Densité par jour pour la grille mensuelle : `total`, `done`, `pending`, `overdue`, `captures` |
| GET/POST | `/v1/entries/{id}/subtasks` | Lister, ajouter |
| PATCH/DELETE | `/v1/subtasks/{id}` | Modifier, cocher, supprimer |
| POST | `/v1/entries/{id}/subtasks/reorder` | **La liste complète ordonnée**, pas un couple (de, vers) : idempotent |
| POST | `/v1/entries/{id}/complete-task` | Termine, et renvoie l'occurrence suivante si la tâche est récurrente |
| POST | `/v1/entries/{id}/reopen` | Rouvre |
| POST | `/v1/entries/{id}/snooze` | Masque jusqu'à un instant. **Ne déplace pas l'échéance** |
| POST | `/v1/entries/{id}/reschedule` | Déplace l'échéance. `null` la retire, ce qui est un acte légitime |
| POST | `/v1/entries/{id}/recurrence` | Définit ou retire une règle. Une règle non prise en charge est **rejetée**, pas approximée |
| POST | `/v1/entries/{id}/pin` | Épingle |
| POST | `/v1/entries/bulk` | Une modification, plusieurs entrées (200 au plus) |

### 14.2 Rappels et notifications

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/v1/reminders` | Rappels programmés. **Aussi la source que le client Windows non empaqueté synchronise** (ADR-040) |
| POST | `/v1/reminders` | Instant absolu, ou décalage (`-15m`, `-1d@18:00`) depuis l'échéance |
| DELETE | `/v1/reminders/{id}` | Annule |
| POST | `/v1/reminders/{id}/dismiss` | Marque traité |
| GET | `/v1/notifications` | Centre de notifications, avec le compteur non lus |
| POST | `/v1/notifications/{id}/read`, `/read-all` | Marque lu |
| PUT | `/v1/devices` | Inscription **idempotente sur `install_id`**, jamais sur le jeton push |
| GET | `/v1/devices` | Appareils. Le jeton n'est **jamais** renvoyé : c'est une capacité de livraison |
| DELETE | `/v1/devices/{install_id}` | Révoque |

### 14.3 Recherche, statistiques, historique, bibliothèque

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/v1/search?q=` | Plein texte + filtres. Renvoie la requête analysée, **y compris `ignored`** |
| GET | `/v1/search/quick?q=` | Palette de commandes : quelques résultats sur plusieurs types |
| GET | `/v1/stats?window_days=` | Tableau de bord analytique |
| GET | `/v1/activity` | Historique utilisateur |
| GET/PATCH/DELETE | `/v1/tags`, `/v1/tags/{id}` | Renommer fusionne vers un tag existant |
| POST | `/v1/tags/{id}/merge` | Fusion explicite |
| POST/DELETE | `/v1/entries/{id}/tags` | Attacher, détacher |
| GET/POST/PATCH/DELETE | `/v1/filters` | Filtres enregistrés |
| GET | `/v1/projects/detailed` | Projets avec compteurs |
| PATCH | `/v1/projects/{id}` | Le slug suit le nom |
| GET | `/v1/projects/{id}/stats` | Complétion d'un projet |

### 14.4 Grammaire de recherche

Une seule grammaire, partagée par la recherche plein texte, la palette et les
filtres enregistrés (`app.domain.search_query`).

| Filtre | Exemples |
| --- | --- |
| `is:` | `is:task`, `is:tâche`, `is:done`, `is:overdue`, `is:recurring`, `is:pinned` |
| `p:` | `p:urgent`, `p:haute`, `p:low` |
| `#tag` | `#finance`, ou `tag:finance` |
| `@projet` | `@refonte`, ou `project:refonte` |
| `due:` | `due:today`, `due:demain`, `due:semaine`, `due:mois`, `due:2026-06-12`, `due:none` |
| `created:` | mêmes valeurs |
| `"phrase"` | expression exacte |

Deux règles gouvernent l'analyse :

1. **Un jeton non reconnu est du texte libre, jamais une erreur.** Quelqu'un qui
   tape `budget: 3000` cherche un budget. Une barre de recherche qui refuse
   l'entrée est une barre de recherche qu'on cesse d'utiliser.
2. **Une *valeur* de filtre inconnue est rapportée, pas devinée.** `p:hgih` ne
   filtre sur rien et apparaît dans `query.ignored`, pour que l'interface puisse
   le dire au lieu de renvoyer silencieusement tout.

Répéter un filtre élargit : `is:task is:idea` signifie « l'un ou l'autre ».

---

## 15. Surface ajoutée en phase 3 — assistant, recherche sémantique, connaissances

### 15.1 Catalogue

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| `POST` | `/v1/assistant/chat` | Poser une question, réponse complète |
| `POST` | `/v1/assistant/chat/stream` | Poser une question, réponse en flux (SSE) |
| `GET` | `/v1/assistant/conversations` | Lister les conversations |
| `GET` | `/v1/assistant/conversations/{id}` | Lire une conversation |
| `POST` | `/v1/search/semantic` | Recherche hybride lexicale + sémantique |
| `GET` | `/v1/search/index-status` | État de l'index sémantique du compte |
| `GET` | `/v1/entities` | Lister les entités détectées |
| `GET` | `/v1/entities/themes` | Sujets récurrents, comptés en SQL |
| `GET` | `/v1/entities/{id}/mentions` | Où une entité a été citée |
| `GET` | `/v1/digests` | Lister les résumés |
| `POST` | `/v1/digests` | Générer un résumé à la demande |
| `POST` | `/v1/digests/{id}/read` | Marquer comme lu |
| `GET` | `/v1/memory` | Tout ce que l'assistant retient |
| `DELETE` | `/v1/memory/{id}` | Oublier définitivement |

**Ce qui est délibérément absent :** aucun endpoint ne déclenche un encodage ou
une extraction à la demande. Ce sont des affaires de worker, et les exposer
laisserait un client transformer une requête HTTP en facture fournisseur non
bornée.

### 15.2 `POST /v1/assistant/chat`

```json
{
  "question": "Que dois-je faire aujourd'hui ?",
  "conversation_id": "018f2c20-…",
  "client_message_id": "c3f1a9e2"
}
```

`client_message_id` porte le même contrat d'idempotence que
`client_capture_id` (ADR-009) : un téléphone qui réessaie sur une connexion
instable ne doit ni poser la question deux fois, ni être facturé deux fois. La
seconde requête renvoie la réponse déjà produite, avec le même `message_id`.

```json
{
  "data": {
    "text": "Aujourd'hui — 2 tâches :\n• Rappeler le DAF de Vinci — 2026-06-10",
    "intent": "today",
    "citations": [],
    "notes": ["Réponse construite depuis vos échéances, sans modèle de langage."],
    "conversation_id": "018f2c20-…",
    "message_id": "018f2c21-…",
    "latency_ms": 38,
    "used_model": false,
    "refused": false
  }
}
```

| Champ | Ce qu'il sert à faire côté client |
| --- | --- |
| `intent` | Choisir le rendu : une liste ne se lit pas comme un paragraphe |
| `citations` | Afficher les sources. Vide sur les routes structurées, qui n'en ont pas |
| `notes` | Dire comment la réponse a été construite. Un assistant qui l'explique est un assistant que l'on peut corriger |
| `used_model` | Afficher instantanément plutôt qu'animer une frappe sur une réponse déjà complète |
| `refused` | Un refus est une réponse légitime (ADR-030), pas une erreur : statut 200 |

### 15.3 `POST /v1/assistant/chat/stream`

Le seul endpoint du produit qui ne renvoie pas du JSON. Deux types d'événements :

```
event: delta
data: {"text": "Deux "}

event: delta
data: {"text": "réunions cette semaine."}

event: answer
data: {"text": "Deux réunions cette semaine.", "intent": "summarise", "citations": [...]}
```

Un client qui ignore les `delta` et ne lit que le dernier `answer` obtient
exactement ce que renvoie l'endpoint non streamé — c'est ce qui rend cet ajout
sûr sans scinder le client en deux chemins de code.

Les routes structurées n'ont rien à streamer : leur réponse est calculée d'un
bloc et arrive en un seul `delta`. L'asymétrie est visible du client, qui affiche
ces réponses instantanément.

L'en-tête `X-Accel-Buffering: no` est envoyé : sans lui, un proxy intermédiaire
tamponne toute la réponse et la délivre d'un coup, ce qui retransforme le
streaming en attente.

### 15.4 `POST /v1/search/semantic`

```json
{ "query": "négociation fournisseur", "limit": 10, "entry_types": ["meeting"] }
```

La réponse porte le détail de la fusion, pas seulement le résultat :

```json
{
  "data": {
    "passages": [
      {
        "chunk_id": "018f…",
        "text": "Le fournisseur a changé ses conditions…",
        "title": "Négociation fournisseur",
        "occurred_at": "2026-06-03",
        "found_by": ["lexical", "semantic"],
        "score": 0.032
      }
    ],
    "took_ms": 24,
    "lexical_count": 12,
    "semantic_count": 8,
    "notes": []
  }
}
```

`found_by` est exposé parce que l'accord entre le sens et les mots est un signal
bien plus fort que l'un ou l'autre seul, et le dire aide l'utilisateur à calibrer
sa confiance. `score` est le score RRF fusionné ; il sert à l'affichage, jamais
au classement côté client.

`notes` porte les dégradations en clair : « Recherche lexicale seule : le service
d'embedding est indisponible », « Aucun résultat sémantique : le corpus n'est pas
encore indexé ». Le produit énonce ses dégradations plutôt que de les masquer.

### 15.5 `GET /v1/search/index-status`

```json
{ "data": { "total_chunks": 412, "pending_chunks": 37, "provider": "openai", "dimensions": 1536 } }
```

Existe pour une raison précise : une recherche sémantique qui ne renvoie rien
parce que le corpus est encore en cours d'indexation et une recherche qui ne
renvoie rien parce qu'aucune réponse n'existe sont **indiscernables** de
l'extérieur. Cet endpoint les distingue.

### 15.6 `GET /v1/memory` et `DELETE /v1/memory/{id}`

Le contenu est retourné **en totalité**, avec le poids après décroissance :

```json
{ "data": [ { "id": "018f…", "kind": "profile", "label": "Profil",
              "statement": "Je dirige le pôle forecast",
              "confidence": 0.95, "weight": 0.87 } ] }
```

Un magasin de mémoire que l'utilisateur ne peut pas inspecter est un magasin
qu'il ne peut pas corriger. La suppression est définitive : la ligne survit en
pierre tombale côté serveur pour qu'une conversation ultérieure ne réapprenne pas
ce qui vient d'être rejeté (ADR-051). Réponse `204`.

### 15.7 Erreurs propres à la phase 3

| Code | Statut | Quand |
| --- | --- | --- |
| `extraction_unavailable` | 503 | Fournisseur injoignable ou saturé. Réessayable |
| `not_found` | 404 | Conversation, entité, résumé ou mémoire inconnus |
| `validation_failed` | 422 | Question vide ou dépassant 2 000 caractères |

Un refus du modèle n'est **pas** une erreur : statut 200, `refused: true`, et le
texte explique. Le transformer en 4xx en ferait une chose que le client réessaie,
ce qui serait un contournement.
