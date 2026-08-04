# MindFlow AI — Exploitation

| | |
| --- | --- |
| **Version** | 1.0 — Phase 4 |
| **Public** | Astreinte, ingénierie plateforme |
| **Complément** | `Deployment.md` pour la mise en production, `Production.md` pour l'exploitation courante |

> Comme `Deployment.md` : **aucune de ces procédures n'a été exécutée en
> conditions réelles.** Elles sont écrites pour être suivies et corrigées, pas
> pour être supposées justes.

---

## 1. Les six signaux qui comptent

Un tableau de bord avec quarante graphiques n'est consulté par personne à trois
heures du matin. Voici ceux qui déclenchent une action.

| Signal | Seuil | Ce qu'il veut dire | Première action |
| --- | --- | --- | --- |
| `captures_lost_total` | **> 0, jamais** | Une capture a été perdue. Le seul indicateur du produit qui doit toujours valoir zéro | Incident. Chercher le `capture_id` dans les logs |
| `embedding_backlog` | Monte pendant 30 min | La recherche sémantique répond depuis un corpus périmé — **indiscernable d'une recherche correcte** | Vérifier le worker planifié et le fournisseur d'embedding |
| `assistant_uncited_answers_total` | Croissance soudaine | Le modèle répond sans passage à l'appui | Vérifier l'index, puis le prompt |
| `integration_syncs_total{outcome="failed"}` | > 20 % sur 1 h | Un fournisseur externe est en panne ou nos jetons sont révoqués | Regarder `last_error` par connexion |
| `reminder_delivery_lag_seconds` p95 | > 120 s | Les rappels arrivent en retard, ce que l'utilisateur remarque immédiatement | Vérifier le worker planifié et Redis |
| `audit_partition_gap` | `true` | Le mois prochain n'a pas de partition. **Chaque insertion d'audit échouera** | `SELECT ensure_audit_partitions(3)` |

**Le dernier est le plus insidieux** : il n'a aucun symptôme avant le 1er du
mois, où il en a beaucoup d'un coup.

---

## 2. Jobs planifiés

| Job | Cadence | Inter-locataires | Si arrêté |
| --- | --- | --- | --- |
| `sweep_job` | 5 min | oui | Les captures dont l'enqueue s'est perdue restent bloquées |
| `dispatch_job` | 10 s | oui | Les événements sortants ne partent plus |
| `reminder_job` | 1 min | oui | Les rappels ne partent plus — visible en minutes |
| `snooze_job` | 15 min | oui | Les tâches reportées ne se réveillent pas |
| `embed_job` | 2 min | oui | Le retard d'encodage monte ; recherche sémantique périmée |
| `extract_job` | 3×/h | oui | Le graphe de connaissances cesse d'être à jour |
| `digest_job` | 1 h | oui | Les résumés cessent d'être produits |
| **`sync_job`** | **5 min** | **oui** | **Les intégrations cessent de se synchroniser.** Le bouton « Synchroniser » reste, donc la panne est discrète |
| **`partition_job`** | **quotidien à 03:11, + au démarrage** | **oui** | **Voir §1, dernière ligne** |

Tous utilisent `privileged_session()` — la seule connexion du produit qui
contourne RLS (ADR-042) — puis rentrent dans une session locataire par compte,
de sorte que chaque écriture passe par une politique.

**Vérifier qu'un job tourne vraiment.** Le piège de la phase 2 : `privileged_session()`
utilisait le mauvais rôle, ne voyait rien, et n'échouait jamais. Un job
inter-locataires qui renvoie systématiquement zéro est suspect, pas rassurant.

```sql
-- Le rôle de maintenance voit-il au-delà d'un locataire ?
SET ROLE mindflow_maintenance;
SELECT count(DISTINCT account_id) FROM entry;  -- doit être > 1 en production
RESET ROLE;
```

---

## 3. Runbooks

### 3.1 « La recherche sémantique ne trouve rien »

```bash
# 1. Le corpus est-il indexé ?
curl -H "Authorization: Bearer $TOKEN" $API/v1/search/index-status
```

`pending_chunks == total_chunks` : rien n'a jamais été encodé. Vérifier
`MINDFLOW_EMBEDDING_BACKEND` — s'il vaut `fake`, le service n'aurait pas dû
démarrer en production, et s'il a démarré c'est que `MINDFLOW_ENV` n'est pas
`prod`.

`pending_chunks` élevé et stable : le worker planifié ne tourne pas.

`pending_chunks == 0` et rien ne sort : le modèle d'embedding a changé sans
réencodage. La recherche filtre sur `embedding_model`, donc elle ignore
délibérément les vecteurs de l'ancien modèle plutôt que de mélanger deux espaces
(ADR-046). Lancer `reset_embeddings()` puis laisser le worker rattraper.

### 3.2 « Une intégration ne se synchronise plus »

```sql
SELECT provider, status, consecutive_failures, last_error, last_sync_at
FROM integration_connection WHERE account_id = :account;
```

| `status` | Signification | Action |
| --- | --- | --- |
| `expired` | Le grant OAuth est révoqué. **Réessayer ne servira jamais** | L'utilisateur doit reconnecter. `sync_job` ne la sélectionne plus |
| `error` | Six échecs consécutifs. Le planificateur a abandonné | Vérifier `last_error`, puis reconnecter |
| `active`, `consecutive_failures > 0` | En retard exponentiel, plafonné à 1 h | Attendre, ou regarder `last_error` |
| `active` avec `last_sync_at` ancien et zéro échec | Le worker ne tourne pas | §2 |

**La dernière ligne est la seule qui accuse le produit** ; les trois autres
accusent le fournisseur. La distinguer coûte une colonne à lire et évite de
chercher une panne chez soi quand c'est un jeton révoqué.

**Ce que `sync_job` ne fait jamais** : retenter une connexion `expired`. Un
grant révoqué ne redevient pas valide, et le retenter en boucle consomme du
quota chez le fournisseur tout en enterrant la seule action utile — demander à
l'utilisateur de reconnecter.

**Le retard d'une connexion en échec se calcule sur `updated_at`**, pas sur
`last_sync_at` : un échec ne met pas à jour `last_sync_at`, parce que cette
colonne signifie « dernier moment où nous étions en phase avec le fournisseur »
et un échec ne nous y a pas mis. Conséquence à connaître : une modification de
la connexion par l'utilisateur touche `updated_at` et peut retarder d'une heure
au plus un réessai.

### 3.3 « Quelqu'un voit des notes qui ne sont pas les siennes »

L'incident le plus grave possible. Dans l'ordre :

```sql
-- 1. Les politiques sont-elles en place et RESTRICTIVE ?
SELECT polname, polpermissive FROM pg_policy
WHERE polname LIKE '%_workspace_visibility';
-- Attendu : deux lignes, polpermissive = f

-- 2. Le rôle applicatif contourne-t-il RLS ?
SELECT rolbypassrls FROM pg_roles WHERE rolname = 'mindflow_app';  -- attendu : f
```

Puis vérifier que le contexte utilisateur est bien posé : la politique
restrictive **passe** quand `app.user_id` est absent, ce qui est la concession
de compatibilité d'ADR-054. Si l'API a cessé de le poser, chaque organisation
devient un disque partagé.

```bash
grep -n "user_id=principal.user_id" app/api/deps.py  # doit renvoyer une ligne
```

### 3.4 « Les partitions d'audit manquent »

`partition_job` tourne tous les jours et au démarrage du worker. S'il manque une
partition, c'est que le job ne tourne pas — vérifier §2 avant de réparer à la
main.

```sql
SELECT ensure_audit_partitions(3);         -- crée ce qui manque
SELECT drop_audit_partitions_before('2025-01-01');  -- rétention
```

`DROP` sur une partition plutôt que `DELETE` : instantané, récupère l'espace, ne
verrouille pas le reste de la table.

| Réglage | Défaut | Effet |
| --- | --- | --- |
| `MINDFLOW_AUDIT_PARTITION_MONTHS_AHEAD` | `3` | Marge de création |
| `MINDFLOW_AUDIT_RETENTION_MONTHS` | `0` | **Rétention désactivée.** Un `DROP` est irréversible : il doit être demandé, jamais subi |

**La jauge `audit_partition_gap` est relue depuis `pg_class` après chaque
passage**, pas déduite du travail que le job croit avoir fait. Si elle reste à 1
alors que le job vient de tourner, ce n'est pas un retard : c'est une fonction
cassée ou un problème de droits, et le journal d'audit tombera le 1er.

### 3.5 Rotation d'une clé de chiffrement

```bash
NEW=$(python -c "from app.infra.crypto import generate_key; print(generate_key())")
# Nouvelle clé en tête, ancienne conservée
MINDFLOW_TOKEN_ENCRYPTION_KEYS="$(date +%Y-%m):$NEW,$OLD_ENTRIES"
```

Les lectures continuent avec l'ancienne clé, les écritures utilisent la
nouvelle. L'ancienne se retire quand plus aucune ligne ne la nomme — sans
fenêtre de maintenance, ce qui est la seule façon qu'une rotation ait
effectivement lieu.

---

## 4. Sauvegardes

| Donnée | Méthode | Fréquence | RPO visé |
| --- | --- | --- | --- |
| PostgreSQL | Sauvegarde continue + snapshot | Continu | 5 min |
| Stockage objet (audio) | Réplication du bucket | Continu | 15 min |
| Redis | **Aucune** | — | Perte acceptée |

**Redis n'est pas sauvegardé, délibérément.** La file est reconstructible : le
balayeur récupère les captures dont l'enqueue s'est perdue, parce que la base
est la source de vérité et pas la file.

> **Une sauvegarde jamais restaurée n'est pas une sauvegarde.** Aucune
> restauration n'a été testée sur ce projet. C'est le premier travail
> d'exploitation à faire, avant toute mise en production réelle.

---

## 5. Sécurité opérationnelle

| Contrôle | Où il vit | Vérifiable par |
| --- | --- | --- |
| Isolation entre comptes | Politique RLS PostgreSQL | `tests/integration/test_rls.py`, table par table |
| Isolation entre espaces | Politique RLS **restrictive** | `tests/integration/test_workspaces.py` |
| Le rôle applicatif ne contourne pas RLS | `NOBYPASSRLS` | Requête du §3.3 |
| Jetons OAuth chiffrés au repos | AES-256-GCM, clé versionnée | `tests/unit/test_crypto.py` |
| Jetons de partage stockés hachés | SHA-256 | Une fuite de base n'est pas une fuite de liens |
| Prompts protégés contre l'injection | Marqueur vérifié par test | `tests/unit/test_prompts.py`, sur **tous** les prompts |
| Aucun endpoint inter-comptes | Absence délibérée | Un « super admin » est une brèche à un identifiant près |

**Un contrôle applicatif sans politique en dessous est une suggestion.** Tout ce
qui est vérifié dans le code l'est aussi dans la base.

---

## 6. Ce qui manque

- Aucun manifeste Kubernetes, aucun `docker-compose` exécuté.
- Aucune alerte configurée : les métriques existent, rien ne les surveille.
- Aucun test de restauration.
- Aucun exercice d'incident.
- Pas de rotation de journaux définie.
- Pas de plan de reprise après sinistre.
