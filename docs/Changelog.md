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

Rien pour l'instant. La phase 2 n'a pas démarré.

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
