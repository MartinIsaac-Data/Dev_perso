# MindFlow AI — Journal des modifications

Toutes les évolutions notables de MindFlow AI sont consignées ici.

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Versionnage sémantique adapté : `MAJEUR.MINEUR.CORRECTIF`.

**Conventions de ce journal**

| Section | Contenu |
| --- | --- |
| `Ajouté` | Nouvelles fonctionnalités |
| `Modifié` | Changements de comportement existant |
| `Déprécié` | Fonctionnalités qui seront retirées |
| `Retiré` | Fonctionnalités supprimées |
| `Corrigé` | Corrections de bogues |
| `Sécurité` | Correctifs de sécurité |
| `Décisions` | ADR créés, modifiés ou remplacés |
| `Documentation` | Évolutions de la documentation de conception |

**Portée** : ce journal couvre l'ensemble du produit — documentation de conception,
back-end, client, infrastructure et modèles IA. Les versions de documentation
(`0.x.y` avant tout code) sont consignées au même titre que les versions logicielles.

---

## [Non publié]

Rien pour l'instant.

---

## [0.5.0] — 2026-08-03

**Phase 4 — Les fonctionnalités d'entreprise.** Le produit passe d'un outil
personnel à un outil d'équipe. **Rien de l'existant n'a été réécrit** : les 35
politiques d'isolation de compte, les prompts de la phase 3 et leurs empreintes,
et l'intégralité des tests antérieurs sont inchangés. 777 tests passent.

### Ajouté — Domaine

- `permissions` : quatre rôles de compte (`owner`, `admin`, `member`, `viewer`)
  et trois rôles d'espace (`editor`, `commenter`, `reader`), ordonnés. `can()`
  est une **fonction totale** : une action inconnue est refusée, jamais autorisée
  par omission.
- `collaboration` : analyse des `@mentions` — avec un `lookbehind` négatif qui
  refuse les adresses de courriel —, émission et vérification des jetons de
  partage. La révocation est vérifiée **avant** l'expiration, parce que c'est ce
  que l'auteur du lien a fait.
- `sync` : classification des synchronisations en `NOOP`, `PULL`, `PUSH`,
  `CONFLICT`, sans aucune E/S. Délai entre tentatives exponentiel, plafonné à
  une heure, abandon après six échecs consécutifs.

### Ajouté — Infrastructure

- `infra/crypto` : AES-256-GCM avec **trousseau versionné**. Format
  `v1$id$base64(nonce‖scellé)`, l'identifiant de clé authentifié comme donnée
  associée. La rotation se fait sans fenêtre de maintenance.
- `infra/sync/connectors` : sept fournisseurs derrière un port unique. Outlook et
  Microsoft To Do partagent un adaptateur Microsoft Graph. Obsidian déclare
  `is_server_side = false` et ne fait aucune E/S serveur.
- Neuf tables : `workspace`, `workspace_member`, `invitation`, `comment`,
  `mention`, `share_link`, `integration_connection`, `external_link`,
  `meeting_session`.

### Ajouté — API

- Espaces, membres, invitations, commentaires, mentions, partage, intégrations,
  conflits (`API.md` §16).
- `/v1/admin/overview`, `/audit`, `/usage`, `/health` (`API.md` §17).
- `GET /v1/shared/{token}` : la **seule** route non authentifiée du produit. Elle
  s'exécute sur une connexion de maintenance et retourne une entrée, par
  identifiant.
- `permission_denied` (403), distinct de `forbidden` : une portée de jeton
  insuffisante et un rôle insuffisant appellent des remèdes différents.

### Sécurité

- **Deux politiques RLS `RESTRICTIVE`** sur `entry` et `comment`. Restrictives et
  non permissives : PostgreSQL combine les permissives par `OR`, donc une seconde
  politique permissive aurait **élargi** l'accès en croyant le restreindre.
- Une note sans espace est privée, y compris pour l'administrateur du compte —
  appliqué par la base, pas par l'API.
- Jetons OAuth chiffrés au repos ; jetons de partage stockés **hachés** en
  SHA-256 et retournés en clair exactement une fois.
- Le service refuse de démarrer en production sans clé de chiffrement, et refuse
  une `PUBLIC_BASE_URL` en `localhost` — qui ferait pointer chaque lien de
  partage sur la machine de l'émetteur.
- Aucun endpoint inter-comptes, aucun « super administrateur ». C'est une absence
  délibérée (`API.md` §17.1).

### Modifié

- `audit_log` est **partitionnée par mois**. Clé primaire composite
  `(id, occurred_at)`. Rétention par `DROP TABLE`.
- Sept index ajoutés, chacun motivé par une requête existante (`Database.md`
  §16.5).
- `NotificationKind` gagne `mention` et `comment`, distincts de `system` : une
  mention est la notification qu'on veut garder en coupant les autres.

### Corrigé

- **Défaut latent de la phase 2** : la migration 0003 n'avait jamais posé
  `ALTER DEFAULT PRIVILEGES` pour `mindflow_maintenance`, rendant invisible à
  tous les travaux inter-locataires **chaque table créée après elle**. Le défaut
  était silencieux — un job qui ne voit rien ne lève pas d'erreur, il ne fait
  rien. Rattrapé en 0006 et 0007.

### Décisions

- [ADR-054] La visibilité par espace est une politique **restrictive**
- [ADR-055] Le compte *est* l'organisation
- [ADR-056] Un conflit de synchronisation est classé, jamais résolu tout seul
- [ADR-057] Un seul port pour sept connecteurs, dont un qui n'est pas un service
- [ADR-058] Les jetons sont chiffrés avec un trousseau versionné
- [ADR-059] Le journal d'audit est partitionné par mois, purgé par `DROP`

### Documentation

- `Deployment.md`, `DevOps.md`, `Production.md`, `UserGuide.md`,
  `RoadmapV2.md`, `RoadmapV3.md` — six documents nouveaux.
- `API.md` §16–17, `Database.md` §16, `Architecture.md` §17, index d'ADR complété
  de 034 à 059.

### Ce qui n'a pas été fait, et qui était demandé

Énoncé plutôt qu'omis. Le détail est dans `Architecture.md` §17.5 et `TODO.md`.

- **IA temps réel pendant les réunions** : la table `meeting_session` existe et
  n'est remplie par rien.
- **Mode hors ligne** : seule la capture l'est, depuis la phase 1.
- **Versions Desktop et Web** : Flutter les cible ; aucun build n'a été produit.
- **Écrans Flutter d'entreprise** : l'API existe, le client ne l'appelle pas.
- **`sync_job` et `partition_job`** : documentés, non écrits. Tant que le second
  n'existe pas, la protection d'ADR-059 repose sur quelqu'un qui y pense.
- **Notifications intelligentes** : les types existent, aucune logique de
  regroupement.
- Aucun appel réel à un fournisseur d'intégration n'a jamais été passé, et aucune
  mesure de charge n'a été faite.

---

## [0.4.0] — 2026-08-03

**Phase 3 — La couche IA.** Le produit passe de « capturer, planifier, retrouver »
à « interroger ». Rien de l'existant n'a été cassé : les 481 tests des phases 1 et
2 passent inchangés, et le prompt d'extraction de la phase 1 conserve la même
empreinte pour que l'historique des `ai_run` reste valide.

### Ajouté — Domaine

- `chunking` : découpage déterministe sur frontières de phrases, hachage de
  contenu, estimation de budget. Aucune dépendance à un tokeniseur — cela
  épinglerait le projet au vocabulaire d'un fournisseur.
- `retrieval` : fusion par rangs réciproques (k = 60). Les scores lexicaux et
  vectoriels ne sont pas commensurables ; la fusion n'utilise que les positions.
- `intent` : routage déterministe des cinq questions imposées.
- `knowledge` : sept catégories d'entités, clés de résolution calculées en code.
- `memory` : contrat des faits durables, décroissance exponentielle de confiance.
- `EmbedderPort` et `ChatPort`, streaming en opération primaire.

### Ajouté — Prompts

- Dossier dédié `app/prompts/`, hors de `app.infra`, avec son propre contrat
  d'imports vérifié par `import-linter`.
- Sept prompts versionnés et empreintés : extraction de note, extraction
  d'entités, extraction de mémoire, réponse citée, trois résumés périodiques,
  narration des thèmes.
- Un test affirme que **tout** prompt manipulant du texte utilisateur déclare que
  ce texte est une donnée et non une instruction.

### Ajouté — Fournisseurs

- OpenAI, Claude, Gemini, Llama (auto-hébergé) et Mistral, derrière deux ports.
  Le choix est une variable d'environnement.
- Un test lit les sources et échoue si un module hors de la fabrique nomme un
  fournisseur.

### Ajouté — Schéma

- Migration 0006 : extension `vector`, tables `chunk`, `entity`,
  `entity_mention`, `conversation`, `conversation_message`, `memory`, `digest`.
- Index HNSW cosinus sur `chunk.embedding`, index partiel sur le retard
  d'encodage.
- RLS activée et forcée sur les sept tables dans la migration qui les crée.

### Ajouté — Services et workers

- Indexation (découpage synchrone, encodage asynchrone), récupération hybride,
  assistant conversationnel, extraction d'entités, mémoire, résumés périodiques.
- Trois jobs planifiés : `embed_job`, `extract_job`, `digest_job`.

### Ajouté — API

- `/v1/assistant/chat` et `/v1/assistant/chat/stream` (SSE), conversations,
  `/v1/search/semantic`, `/v1/search/index-status`, `/v1/entities`,
  `/v1/entities/themes`, `/v1/digests`, `/v1/memory`.

### Ajouté — Client

- Écran d'assistant avec réponse en flux et citations rendues sous chaque
  réponse générée.
- Écran de connaissances : entités, sujets récurrents, mémoire — inspectable et
  supprimable en un geste.
- Fil de résumés. Trois entrées ajoutées à la palette ⌘K.

### Modifié

- `app/infra/ai/prompts.py` devient un réexport de `app.prompts.extraction` :
  mêmes noms, même texte, même empreinte.
- `harden_schema` passe en API publique du domaine, désormais partagée par trois
  contrats de décodage contraint.
- La création et la modification d'une entrée réindexent ; la suppression
  logique retire ses chunks.
- Le contrat de configuration de production exige désormais un `embedding_backend`
  et un `chat_backend` réels. Le faux encodeur produit des vecteurs qui
  s'indexent et se retrouvent **avec succès** et n'encodent rien : la recherche
  sémantique aurait l'air de fonctionner en renvoyant les mauvaises notes.

### Corrigé

- **Privilèges du rôle de maintenance.** La migration 0003 avait posé des
  privilèges par défaut pour `mindflow_app` et `mindflow_readonly` mais pas pour
  `mindflow_maintenance` : toute table créée après elle — dont les cinq de la
  phase 2 — était invisible à la connexion inter-locataires. Sans erreur et sans
  symptôme jusqu'à ce qu'un job de fond en ait besoin.
- **Ordre des écritures à la réindexation.** SQLAlchemy émet les insertions
  avant les suppressions pour un même mapper ; un chunk remplaçant un autre au
  même index violait la contrainte d'unicité — le cas ordinaire d'une note
  modifiée.
- **Compteurs d'entités périmés.** Une entité retirée d'une réextraction
  conservait son compteur de la veille, faute d'être recomptée.
- **Routage des accents et apostrophes.** « que dois je faire aujourd hui »,
  produit couramment par la dictée, ne routait pas comme la forme accentuée.

### Décisions

- ADR-045 — Aucun fournisseur d'IA n'est couplé au projet : le port est le contrat
- ADR-046 — La largeur du vecteur est une décision de déploiement
- ADR-047 — Ce que la base sait exactement ne passe jamais par un modèle
- ADR-048 — Une question n'est pas une requête de recherche
- ADR-049 — La résolution d'entités est déterministe, l'extraction ne l'est pas
- ADR-050 — Le découpage est synchrone et gratuit, l'encodage asynchrone et payant
- ADR-051 — La mémoire ne retient que le durable, et l'oubli est définitif
- ADR-052 — Les résumés reçoivent leurs chiffres comme des faits établis
- ADR-053 — Les prompts sont des artefacts versionnés, dans un dossier dédié

### Documentation

- `AI.md` §13 — la couche IA telle qu'implémentée, **y compris les six écarts
  avec la conception de la phase 0** et ce que le système ne garantit pas.
- `Database.md` §15, `API.md` §15, `Architecture.md` §16.

### Tests

599 tests back-end (dont 179 nouveaux), 108 tests client, 5 contrats d'imports.

---

## [0.3.0] — 2026-08-03

**Phase 2 — Planification, recherche et mesure.** Le produit passe de « capturer
et consulter » à « capturer, planifier, retrouver et mesurer ». Aucune décision
des phases précédentes n'a été renversée ; deux défauts silencieux de la phase 1
ont été corrigés (ADR-041, ADR-042).

### Ajouté — Back-end

| Domaine | Contenu |
| --- | --- |
| Agenda | Vues jour / semaine / mois, bornes calculées dans le fuseau de l'utilisateur, retards dans leur propre section |
| Calendrier | Densité par jour agrégée en base, grille de semaines entières |
| Tâches avancées | Sous-tâches ordonnées, récurrence RRULE (sous-ensemble), report, replanification, épinglage, opérations groupées |
| Rappels | Décalages automatiques (`-1d@18:00`, `-15m`) re-dérivés à chaque changement d'échéance, rappels manuels jamais réécrits |
| Notifications | Centre en base écrit **avant** toute tentative de push, FCM (HTTP v1) et WNS, adaptateurs derrière un port |
| Recherche | Colonne générée `tsvector` + index GIN, grammaire `is:` `p:` `#tag` `@projet` `due:`, palette de commandes |
| Statistiques | Complétion, délai médian, séries, répartitions, et les chiffres qui dérangent |
| Historique | Table `activity_event` avec libellé dénormalisé, distincte de l'audit et des corrections IA |
| Bibliothèque | Tags avec fusion, projets avec compteurs, filtres enregistrés |

5 tables, 22 colonnes, 12 index et 1 conversion de type dans la migration 0005.
25 nouveaux points d'API. 311 tests passent ; `ruff`, `mypy --strict` (84
fichiers) et `lint-imports` (4/4) sont propres.

### Ajouté — Client Flutter

| Écran | Rôle |
| --- | --- |
| Agenda | Slivers par jour, en-têtes collants, retards en tête |
| Calendrier | Grille mensuelle, densité en points, anneau pour les retards |
| Palette de commandes | ⌘K : actions puis contenu, navigation au clavier |
| Recherche | Filtres rendus en chips, y compris ceux que le serveur a ignorés |
| Statistiques | Graphiques peints à la main, section « Ce qui ne va pas » |
| Historique | Timeline avec rail, verbes au passé |
| Notifications | Centre, marquage lu, badge dans la navigation |
| Bibliothèque | Projets, tags (fusion par renommage), filtres enregistrés |
| Détail d'une tâche | Sous-tâches, rappels, récurrence, priorité, report, historique |

Nouveau système de design (jetons, palette, thème clair/sombre conçus
séparément), coque adaptative (barre latérale ou barre basse). 90 tests passent,
`flutter analyze` est propre.

### Corrigé

Deux défauts de la phase 1, tous deux silencieux, tous deux trouvés en
implémentant la phase 2 :

- **Les travaux inter-tenants ne voyaient rien** (ADR-042). `privileged_session()`
  utilisait le rôle applicatif, `NOBYPASSRLS` par construction : le balayeur de
  captures et le répartiteur d'outbox traitaient zéro ligne depuis le premier
  jour, sans erreur ni log. Deux tests gardent désormais la propriété.
- **Les horodatages étaient naïfs** (ADR-041). 32 colonnes en `timestamp`
  comparées comme de l'heure locale : filtrage impossible contre un datetime
  aware, et regroupement par jour décalé du fuseau. Converties en `timestamptz`.

Et un défaut introduit puis corrigé pendant la phase : la seconde clé étrangère
de `task` vers `entry` rendait la relation ORM ambiguë et faisait échouer toute
la suite d'intégration jusqu'à ce que `foreign_keys` soit déclaré explicitement.

### Décisions

| ADR | Décision | Coût accepté principal |
| --- | --- | --- |
| ADR-037 | Recherche sur colonne générée `tsvector`, `websearch_to_tsquery` | Moins expressif qu'un `to_tsquery`, mais ne peut pas lever d'exception |
| ADR-038 | Le fournisseur de push est stocké par appareil, pas déduit | Une colonne de plus, et un client qui doit dire la vérité |
| ADR-039 | Une charge push est un pointeur, jamais une copie du contenu | Aperçu moins riche sur l'écran verrouillé |
| ADR-040 | Windows non empaqueté programme ses notifications localement | Un rappel local n'arrive que si l'application a tourné depuis |
| ADR-041 | Tous les horodatages en `timestamptz` | Une réécriture de table par colonne convertie |
| ADR-042 | Connexion dédiée pour les travaux inter-tenants | Une variable d'environnement et un rôle à provisionner |
| ADR-043 | Une sous-tâche n'est pas une entrée ; un seul niveau | On ne peut ni taguer ni rechercher une sous-tâche |
| ADR-044 | L'occurrence suivante part de l'échéance, pas de la complétion | Une tâche jamais terminée n'engendre rien |

### Compromis retenus

| Compromis | Gagné | Payé |
| --- | --- | --- |
| Agrégation en SQL plutôt qu'en Python | Le calendrier et les statistiques restent rapides à 50 000 entrées | Des requêtes plus difficiles à lire |
| Graphiques peints à la main | Aucune dépendance de plus, un seul passage de peinture | Deux types de graphiques, pas davantage |
| Palette de commandes plutôt qu'une navigation qui grandit | Ajouter un écran ne coûte pas un onglet | Une fonctionnalité invisible à qui n'essaie jamais ⌘K |
| Ordonnancement clairsemé (100, 200, 300) | Un déplacement réécrit une ligne | Une renumérotation quand l'espace manque |
| Réordonnancement par liste complète | Idempotent sur un lien instable | Une charge un peu plus grosse |
| Notification écrite avant le push | Rien n'est perdu si l'appareil est injoignable | Des notifications non lues qui s'accumulent |
| Deux chemins de notification Windows | Le poste de travail est réellement servi | Deux comportements à documenter et à tester |

### Améliorations proposées pour la phase 3

1. **Reprise automatique du mode dégradé** — toujours pas faite, et toujours la
   dette la plus coûteuse : les captures traitées quota atteint ne sont jamais
   reprises.
2. **Corpus d'évaluation annoté** (AI.md §7). La phase 2 mesure le taux de
   correction ; sans corpus, on ne sait toujours pas si une modification de
   prompt l'améliore.
3. **Pagination par curseur exposée au client** — la recherche et l'agenda
   chargent une page fixe.
4. **Synchronisation multi-appareils** (API.md §9), maintenant que plusieurs
   appareils sont réellement enregistrés.
5. **RAG** pour le rattachement aux projets, qui repose encore sur une
   correspondance floue de libellés.
6. **Tests de bout en bout du client** contre un back-end réel.
7. **Budget de coût par compte** — le coût est affiché, aucun plafond n'est
   appliqué.

### Non fait, sciemment

- **`docker compose up` n'a toujours pas été exécuté** : pas de démon Docker dans
  l'environnement de développement. Seule la CI valide ce chemin.
- **Aucun build Android, iOS ou Windows produit.** La CI les compile ; le chemin
  de notification Windows n'a donc jamais été exécuté sur un vrai poste.
- **Le graphe d'activité ne propose pas de zoom** ni d'export : hors périmètre.

---

## [0.2.0] — 2026-08-03

**Phase 1 — MVP fonctionnel.** Premier code applicatif. Le produit décrit en phase 0
tourne de bout en bout : on parle, la voix est transcrite, un modèle en extrait une
structure typée, et le résultat est stocké et consultable. Aucune décision de la
phase 0 n'a été renversée ; cinq ADR ont été ajoutés pour combler ce que la
conception n'avait pas prévu (ADR-029 à ADR-036).

### Ajouté — Back-end (FastAPI)

| Domaine | Contenu |
| --- | --- |
| Structure | Monolithe modulaire `api` → `services` → `domain`, avec `infra` et `workers` ; les 4 contrats d'`import-linter` échouent la CI si un module traverse une frontière |
| Base de données | 20 tables, migrations Alembic (schéma, RLS, rôles applicatifs, politique de recherche d'identité), montée **et descente** vérifiées en CI |
| Isolation | Row Level Security sur les 15 tables porteuses de `account_id`, `SET LOCAL app.account_id` par transaction, 23 tests d'isolation table par table |
| Authentification | Vérification locale des jetons Supabase (HS256 ou JWKS), provisionnement paresseux du compte |
| Capture | Déclaration idempotente, URL d'envoi signée, `complete` idempotent, transaction fermée avant la mise en file |
| Chaîne IA | Whisper → garde-fous anti-hallucination → LLM en sortie structurée stricte → résolution déterministe des dates → écriture |
| Ports | `TranscriberPort`, `AnalyzerPort`, `ObjectStoragePort`, `TaskQueuePort` — chaque moteur est remplaçable par configuration |
| API | REST versionnée, enveloppes `data`, erreurs RFC 9457 avec code applicatif stable, Swagger complet |
| Exploitation | Journalisation structurée avec identifiant de corrélation, métriques Prometheus, `/health` et `/ready` |
| Livraison | Dockerfile multi-étapes, `docker-compose.yml` (postgres, redis, migrations one-shot, api, worker), CI en 4 étages |

138 tests passent. `ruff`, `mypy --strict` (64 fichiers) et `lint-imports` (4/4) sont
propres. Couverture du domaine : 94 % pour un plancher de 85 %.

### Ajouté — Client (Flutter)

| Écran | Rôle |
| --- | --- |
| Connexion | Connexion et création de compte, un seul formulaire à deux modes |
| Tableau de bord | Compteurs, échéances proches, quota, file d'attente hors ligne |
| Liste des notes | Recherche et filtres exécutés côté serveur, complétion, suppression |
| Détail d'une note | Édition, échéance avec son expression d'origine, lien vers l'enregistrement |
| Enregistrement vocal | Micro, niveau d'entrée, envoi, suivi du traitement |
| Lecture audio | Audio d'origine, transcription, éléments extraits |

54 tests passent, `flutter analyze` est propre.

### Décisions

| ADR | Décision | Coût accepté principal |
| --- | --- | --- |
| ADR-029 | Supabase Auth vérifié localement, jamais d'appel réseau sur le chemin de requête | Deux schémas de signature à gérer (HS256 et JWKS) |
| ADR-030 | Sortie structurée stricte : un JSON non conforme est rejeté, jamais rattrapé | Une capture peut échouer à l'extraction ; sa transcription reste |
| ADR-031 | Balayeur de captures bloquées : la file est un cache, la base est la vérité | Une tâche périodique de plus |
| ADR-032 | Cible Python `>=3.11` au lieu de 3.13 | Quelques optimisations de version non utilisées |
| ADR-033 | Rôle applicatif `NOSUPERUSER`, `NOBYPASSRLS` obligatoire | Un rôle à provisionner dans chaque environnement |
| ADR-034 | File de captures persistée sur l'appareil avant tout appel réseau | Un fichier JSON réécrit en entier à chaque modification |
| ADR-035 | Fuseau IANA de l'appareil transmis à chaque capture | Une dépendance de plus, et un repli faillible hors d'Europe |
| ADR-036 | Mode d'authentification locale pour le développement, verrouillé par trois barrières | Un chemin d'authentification supplémentaire à maintenir |

### Corrigé

Défauts trouvés à l'implémentation et corrigés avant livraison. Chacun aurait été un
incident en production :

- **La RLS était inerte.** `FORCE ROW LEVEL SECURITY` ne s'applique pas aux
  superutilisateurs : l'application connectée en `postgres` contournait toutes les
  politiques. Rôle dédié + test qui vérifie `rolsuper is false` (ADR-033).
- **Interblocage sur verrou de ligne.** Les `BackgroundTasks` de FastAPI s'exécutent
  *avant* la fermeture des dépendances : la transaction de requête tenait encore la
  ligne que le worker tentait de mettre à jour. `complete_capture` gère désormais sa
  propre transaction et met en file strictement après le `commit`.
- **`create_app(settings)` était sans effet** : les dépendances lisaient le singleton
  global, donc les tests atteignaient un vrai Redis. Elles lisent `app.state.settings`.
- **Les garde-fous anti-hallucination étaient par moteur**, donc contournés par le
  moteur de test. Déplacés dans l'orchestrateur : « chaque moteur » (AI.md §3.2) veut
  dire chaque moteur.
- **Les boucles Whisper d'un seul mot passaient au travers** du détecteur de n-grammes
  (7 mots < 2 × fenêtre de 4). Ajout d'un contrôle de dominance d'unigramme.
- **`après-demain` était résolu comme `demain`** : le tiret n'était pas normalisé. La
  correction ne convertit les tirets qu'entre lettres, pour ne pas casser `12-06-2026`.
- **Valeurs par défaut ORM uniquement** : les insertions SQL brutes violaient des
  contraintes `NOT NULL`. `server_default` partout, et `compare_server_default` activé
  pour qu'Alembic détecte la dérive.
- **Le conftest avalait un échec de `downgrade`**, laissant la base de test sur un
  schéma périmé. Remplacé par une reconstruction complète, sans chemin silencieux.

### Compromis retenus

| Compromis | Gagné | Payé |
| --- | --- | --- |
| Monolithe modulaire plutôt que micro-services | Une seule transaction, un seul déploiement, un débogage simple | Une discipline d'imports à faire respecter par outillage, pas par bonne volonté |
| RLS en base plutôt que filtrage applicatif | L'isolation tient même si une requête oublie son `WHERE` | Un rôle non-superutilisateur obligatoire, et un `SET LOCAL` par transaction |
| Sortie structurée stricte plutôt que réparation de JSON | Aucune donnée inventée par une heuristique de rattrapage | Un taux d'échec d'extraction non nul, assumé et visible |
| Résolution des dates en code plutôt que par le modèle | Déterministe, testable, correcte au changement d'heure | Un module à maintenir, langue par langue |
| Sondage plutôt que SSE côté client | Aucune connexion longue à gérer sur mobile | Quelques requêtes de plus par capture |
| Fichier JSON plutôt que SQLite pour la file locale | Aucune dépendance embarquée | Réécriture intégrale à chaque modification |
| Quota qui dégrade au lieu de bloquer | Une pensée n'est jamais perdue pour une raison commerciale | Un plafond absolu à part, pour l'abus |

### Améliorations proposées pour la phase 2

Par ordre de valeur décroissante :

1. **Mesurer avant d'optimiser.** Le dispositif d'évaluation d'`AI.md` §7 n'existe
   qu'en conception. Sans corpus annoté, toute évolution du prompt est un pari. C'est
   le préalable à tout le reste.
2. **Reprise automatique du mode dégradé.** Les captures traitées en mode dégradé
   (quota atteint) ne sont aujourd'hui jamais reprises automatiquement. Un balayeur
   au retour du quota mensuel manque.
3. **RAG.** L'architecture est décrite (AI.md §6), rien n'est implémenté. La
   désambiguïsation des projets repose sur une correspondance floue de libellés, ce
   qui plafonnera vite.
4. **Synchronisation multi-appareils.** La file locale gère « ce qui n'est pas encore
   parti », pas « ce que l'autre appareil a modifié ». Le protocole d'API.md §9 reste
   à implémenter.
5. **Notifications d'échéance.** Une tâche extraite mais jamais rappelée ne vaut pas
   grand-chose. C'est la fonctionnalité la plus demandée par les personas du PRD.
6. **Tests de bout en bout du client** contre un back-end réel, avec `patrol` ou
   `integration_test`. Les tests actuels couvrent la logique, pas l'assemblage.
7. **Budget de coût par compte.** `PRICING_MICRO_EUR_PER_TOKEN` est renseigné mais
   aucun plafond n'est appliqué par compte.

### Non fait, sciemment

- **`docker compose up` n'a pas été exécuté** dans l'environnement de développement :
  aucun démon Docker n'y tourne. La composition est vérifiée par relecture et par la
  CI (étage `image`), pas par exécution locale.
- **Aucun build Android ou iOS n'a été produit.** Les dossiers de plateforme sont des
  artefacts d'outil, régénérés par `flutter create` ; la CI les génère et compile.

---

## [0.1.0-design] — 2026-08-02

**Phase 0 — Conception.** Première version complète de la documentation de
conception. Aucun code applicatif n'a été écrit ; le produit est entièrement décrit
et ses arbitrages sont consignés.

### Ajouté — Documentation

| Document | Contenu |
| --- | --- |
| `PRD.md` | Vision produit, analyse du problème, 5 personas, 13 cas d'utilisation, parcours utilisateur, flux, wireframes ASCII, périmètre MVP et premium, métriques de succès |
| `Architecture.md` | Style architectural, moteurs de qualité, diagrammes C4 (niveaux 1 à 4), 6 diagrammes de séquence, choix techniques justifiés, architecture Flutter et FastAPI, découpage modulaire, carte d'extraction en micro-services, gestion des erreurs, sécurité, observabilité, CI/CD, capacité et coûts |
| `Decisions.md` | 28 ADR au format Contexte → Décision → Alternative écartée → Coût accepté → Réexamen, plus 8 questions ouvertes explicitement non tranchées |
| `Database.md` | Modèle de données complet, diagrammes entité-relation, 40 tables spécifiées en DDL PostgreSQL, politiques RLS, stratégie d'indexation, recherche hybride, rétention, volumétrie prévisionnelle |
| `API.md` | Conventions de nommage, catalogue des ressources, taxonomie d'erreurs RFC 9457, pagination par curseur, idempotence, synchronisation client, SSE, quotas, versionnage, webhooks |
| `AI.md` | Chaîne de traitement en 7 étages, stratégie STT, contrat d'extraction, résolution déterministe, architecture RAG complète, stratégie de modèles et de coûts, dispositif d'évaluation, garde-fous de sécurité, limites connues |
| `Roadmap.md` | Trajectoire v0.1 → v3.0, une question par version, critères de sortie, branches alternatives, chantiers transverses |
| `Sprint01.md` | Plan du sprint 1 — fondations : schéma, RLS, CI, authentification |
| `Sprint02.md` | Plan du sprint 2 — tranche verticale de bout en bout |
| `Sprint03.md` | Plan du sprint 3 — évaluation, mesure et arbitrages |
| `Changelog.md` | Ce document |
| `TODO.md` | Dette de conception, points ouverts, préalables au développement |

### Décisions

28 ADR consignés. Les plus structurants :

| ADR | Décision | Coût accepté principal |
| --- | --- | --- |
| ADR-001 | Monolithe modulaire plutôt que micro-services | La discipline modulaire ne tient que si elle est outillée |
| ADR-004 | PostgreSQL + pgvector, pas de base vectorielle dédiée | Rappel HNSW dégradé sous filtre étroit |
| ADR-005 | Isolation par Row Level Security | Surcharge de requête, pièges de pool de connexions |
| ADR-007 | STT auto-hébergé avec repli SaaS | Opérer un nœud GPU ; le repli élargit la surface de données |
| ADR-008 | Claude pour l'extraction structurée | Dépendance fournisseur sur le chemin critique |
| ADR-009 | Capture offline-first et idempotence client | Moteur de synchronisation complexe |
| ADR-012 | Pas de chiffrement de bout en bout au MVP | MindFlow peut techniquement lire les données de ses utilisateurs — doit être dit explicitement |
| ADR-020 | Résolution temporelle déterministe, pas par le LLM | Couverture linguistique à construire manuellement |
| ADR-026 | Le quota ne bloque jamais une capture | Coût non couvert sur les dépassements |
| ADR-027 | L'édition utilisateur prime sur le retraitement IA | Les entrées corrigées ne bénéficient pas des améliorations du modèle |

Statuts : 21 acceptées ✅, 5 à réexaminer 🔄, 2 provisoires ⚠️.

### Compromis techniques retenus — synthèse de phase

| # | Compromis | Ce qui est gagné | Ce qui est payé |
| --- | --- | --- | --- |
| 1 | Monolithe modulaire | Vitesse de développement, refactoring peu coûteux | Mise à l'échelle par bloc, discipline à outiller |
| 2 | Un seul magasin (PostgreSQL) | Cohérence transactionnelle, RLS sur la recherche | Plafond de performance vectorielle vers 10–20 M de chunks |
| 3 | Flutter | Un code base pour 3 plateformes | La partie la plus critique (audio) reste native |
| 4 | Python partout | Proximité de l'écosystème IA, un seul langage serveur | Débit brut inférieur, GIL |
| 5 | STT auto-hébergé | Coût marginal effondré, audio qui ne sort pas | Nœud GPU à opérer, repli à maintenir |
| 6 | Extraction par un modèle propriétaire | Qualité et respect de schéma décisifs | Coût dominant, dépendance fournisseur |
| 7 | Résolution déterministe des dates | Fiabilité, coût nul, pas d'erreur silencieuse | Chaque langue est un travail explicite |
| 8 | Offline-first | Le principe fondateur du produit est tenu | La partie la plus complexe du client |
| 9 | Table outbox plutôt que bus de messages | Cohérence transactionnelle sans opérer Kafka | Latence de propagation, pas de rejeu historique |
| 10 | Pas de chiffrement de bout en bout | Le produit peut exister | Argument de confiance sacrifié, à assumer publiquement |

### Écarts identifiés et non résolus

Consignés comme tels plutôt que dissimulés :

| # | Écart | Ampleur | Traitement prévu |
| --- | --- | --- | --- |
| E1 | Coût unitaire estimé (0,0100 €) contre objectif PRD (0,004 €) | ×2,5 | Arbitrage au sprint 3 sur données réelles — `AI.md` §7.3 |
| E2 | Économie du MVP non rentable à 5 000 utilisateurs actifs | −0,42 €/UAM | Attendu ; point mort à 8 % de conversion ou −66 % de coût IA |
| E3 | Répartition d'aiguillage (35/55/10) non mesurée | Inconnue | Première mesure au sprint 3 — ADR-019 reste ⚠️ |
| E4 | Rappel HNSW sous filtre étroit non mesuré | Inconnue | Bascule vers parcours exact prévue, à valider |
| E5 | Latence de capture de 300 ms non vérifiée sur appareil | Inconnue | Mesure au sprint 2 |

### Documentation — conventions établies

- Tous les documents de conception vivent dans `/docs` et sont versionnés avec le code.
- Une pull request qui modifie une décision d'architecture sans mettre à jour
  `Decisions.md` est refusée.
- Chaque fin de phase produit : mise à jour de la documentation, ADR des décisions
  prises, explicitation des compromis, propositions d'amélioration pour la phase
  suivante.
- Les chiffres estimés sont marqués comme tels et remplacés par des mesures dès
  qu'elles existent.

### Note de contexte

MindFlow AI est un produit nouveau et indépendant du projet *Transformation OS*
présent à la racine de ce dépôt. Les deux ne partagent ni code, ni base de données,
ni cycle de vie. Cette séparation est intentionnelle et doit être maintenue.

---

## Modèle pour les entrées futures

```
## [x.y.z] — AAAA-MM-JJ

### Ajouté
- …

### Modifié
- …

### Corrigé
- …

### Sécurité
- …

### Décisions
- ADR-0xx — … (statut)

### Compromis retenus
| Compromis | Gagné | Payé |

### Améliorations proposées pour la phase suivante
- …
```
