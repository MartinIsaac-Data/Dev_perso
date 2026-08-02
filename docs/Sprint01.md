# Sprint 01 — Fondations

> **Phase 0 — Conception.** Ce document est un **plan de sprint**, pas un compte rendu.
> Aucun code n'est écrit à ce stade. Les tâches sont estimées en points, la vélocité
> initiale est une hypothèse à corriger dès le sprint 2.

| | |
| --- | --- |
| **Sprint** | 01 · Durée 2 semaines |
| **Version cible** | v0.1 — Fondations |
| **Équipe** | 1 architecte, 2 back-end, 1 mobile, 1 IA (temps partagé) |
| **Capacité** | 34 points (hypothèse initiale, à recalibrer) |

---

## Plan de développement — vue d'ensemble des sprints

Contexte des sprints 1 à 3 dans la trajectoire complète (détail dans `Roadmap.md`).

| Sprint | Version | Thème | Question à laquelle il répond |
| --- | --- | --- | --- |
| **01** | v0.1 | **Fondations** | La base, la sécurité et la CI tiennent-elles ? |
| **02** | v0.1 | **Tranche verticale** | Une capture traverse-t-elle toute la chaîne ? |
| **03** | v0.1 | **Boucle démontrable** | La qualité est-elle mesurable et le coût connu ? |
| 04 | v0.5 | Hors ligne et synchronisation | Peut-on capturer sans réseau, sans perte ? |
| 05 | v0.5 | Structuration riche | Multi-éléments, projets, dates : est-ce juste ? |
| 06 | v0.5 | Recherche et correction | Le corpus est-il exploitable ? |
| 07 | v1.0 | Widgets et rappels | La capture est-elle assez rapide ? |
| 08 | v1.0 | Facturation et conformité | Peut-on ouvrir légalement et commercialement ? |
| 09 | v1.0 | Onboarding et durcissement | La première impression tient-elle ? |
| 10–13 | v1.1 | Réunions, diarisation, partage | Les gens paient-ils ? |
| 14–17 | v1.2 | Intégrations, qualité, langues | Le corpus garde-t-il de la valeur ? |
| 18–24 | v2.0 | Collaboration et entreprise | L'usage en équipe existe-t-il ? |

---

## 1. Objectif du sprint

> **À la fin du sprint 1, l'équipe dispose d'un socle sur lequel on peut construire
> sans avoir à y revenir : schéma complet et isolé, CI qui refuse le mauvais code,
> environnements reproductibles, authentification fonctionnelle.**

Aucune fonctionnalité utilisateur n'est livrée. C'est assumé : les décisions prises ce
sprint (RLS, structure modulaire, migrations) sont celles dont le coût de correction
est le plus élevé une fois du code écrit par-dessus.

### Critère de réussite unique

Un développeur clone le dépôt, lance une commande, et obtient un environnement
complet avec des données de test. Une pull request qui viole une règle
d'architecture, expose une donnée d'un autre locataire, ou casse le typage est
refusée automatiquement.

---

## 2. Périmètre

### Inclus

| # | Élément | Référence |
| --- | --- | --- |
| 1 | Structure du dépôt et découpage modulaire | `Architecture.md` §7.1, §8 |
| 2 | Environnement local reproductible | `Architecture.md` §13.5 |
| 3 | Schéma PostgreSQL complet et migrations | `Database.md` §5 |
| 4 | Row Level Security sur toutes les tables | `Database.md` §6 |
| 5 | Test d'isolation multi-locataire | `Database.md` §6.5 |
| 6 | Squelette FastAPI, middlewares, gestion d'erreurs | `Architecture.md` §7.2, `API.md` §6 |
| 7 | Authentification par lien magique + rotation des jetons | `API.md` §4 |
| 8 | Pipeline CI complet et bloquant | `Architecture.md` §13.2 |
| 9 | Observabilité : journaux, traces, métriques | `Architecture.md` §12 |
| 10 | Squelette Flutter et structure de projet | `Architecture.md` §6.2 |
| 11 | Infrastructure staging en Terraform | `Architecture.md` §14 |

### Exclus explicitement

Toute fonctionnalité de capture, STT, LLM, recherche, interface utilisateur au-delà
d'un écran de connexion. Ces éléments arrivent au sprint 2.

---

## 3. Backlog

### EPIC 1 — Socle du dépôt *(5 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 1.1 | Structure de dossiers back-end | 1 | Arborescence de `Architecture.md` §7.1, modules vides mais présents |
| 1.2 | `pyproject.toml`, outillage | 1 | ruff, mypy strict, pytest, import-linter |
| 1.3 | Configuration `import-linter` | 2 | Contrats de couplage de `Architecture.md` §8.2 |
| 1.4 | `docker compose` local | 1 | PostgreSQL 17 + extensions, Redis, MinIO |

**Point d'attention 1.3** : les contrats d'architecture doivent être écrits avant le
code, pas après. Un contrat ajouté sur du code existant est un contrat qu'on assouplit.

### EPIC 2 — Base de données *(11 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 2.1 | Migration : extensions et fonctions partagées | 1 | pgvector, pg_trgm, unaccent, `current_account_id()` |
| 2.2 | Migration : domaine Identité | 2 | 5 tables + contraintes |
| 2.3 | Migration : domaine Capture | 2 | 3 tables, machine à états en `CHECK` |
| 2.4 | Migration : domaine Connaissance | 3 | 9 tables, spécialisations, liens |
| 2.5 | Migration : Recherche, Intelligence, Plateforme | 2 | chunk avec `vector(1024)`, ai_run, outbox |
| 2.6 | Migration : Facturation, Conformité, Intégrations, Partage | 1 | Tables restantes |

**Décision de séquencement** : tout le schéma est posé dès le sprint 1, y compris les
tables des versions ultérieures. Raison : les contraintes de clé étrangère et les
politiques RLS forment un tout cohérent qu'il est plus coûteux d'assembler par
morceaux. Les tables inutilisées ne coûtent rien.

### EPIC 3 — Sécurité de la base *(8 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 3.1 | Politiques RLS sur toutes les tables concernées | 3 | `USING` + `WITH CHECK`, `FORCE ROW LEVEL SECURITY` |
| 3.2 | Rôles de base et privilèges | 2 | Les 5 rôles de `Database.md` §6.3 |
| 3.3 | Gestion du contexte de session | 2 | `SET LOCAL` en début de transaction, retrait garanti |
| 3.4 | **Test d'isolation automatisé** | 1 | Parcourt chaque table, tente une lecture croisée |

**Point critique 3.3** : `SET LOCAL` et non `SET`. Avec un pool de connexions, un
`SET` global fuiterait le contexte d'un locataire vers la requête suivante. Ce piège
doit être couvert par un test dédié, pas seulement par une revue.

### EPIC 4 — Squelette API *(7 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 4.1 | Application FastAPI, configuration validée au démarrage | 1 | Settings Pydantic ; un paramètre manquant fait échouer le lancement |
| 4.2 | Middleware de corrélation | 1 | `request_id`, `trace_id`, propagation |
| 4.3 | Middleware d'erreurs → RFC 9457 | 2 | Taxonomie de `Architecture.md` §10.2, catalogue de `API.md` §6.2 |
| 4.4 | Middleware de tenancy | 1 | Pose le contexte RLS |
| 4.5 | Endpoints de santé et de préparation | 1 | `/health`, `/ready` avec vérification des dépendances |
| 4.6 | Génération OpenAPI 3.1 | 1 | Publiée, versionnée, testée en contrat |

### EPIC 5 — Authentification *(6 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 5.1 | Lien magique : demande et envoi | 2 | Jeton à usage unique, 15 min, lié à l'appareil |
| 5.2 | Vérification et émission des jetons | 2 | Accès 15 min + rafraîchissement 60 j |
| 5.3 | Rotation et détection de rejeu | 2 | Réutilisation détectée → révocation de la famille |

**Point d'attention 5.3** : la détection de rejeu est la partie de l'authentification
la plus facile à mal faire et la plus difficile à corriger après coup. Elle est
implémentée dès maintenant, avec ses tests.

### EPIC 6 — CI/CD *(6 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 6.1 | Workflow de contrôles rapides | 1 | ruff, mypy strict, import-linter — bloquants |
| 6.2 | Workflow de tests | 2 | PostgreSQL réel en service, seuils de couverture |
| 6.3 | Workflow de sécurité | 1 | pip-audit, bandit, semgrep, gitleaks |
| 6.4 | Build et signature d'image | 1 | Multi-étages, non root, SBOM, cosign |
| 6.5 | Contrôles de migration | 1 | Downgrade testé, `CONCURRENTLY` vérifié |

### EPIC 7 — Observabilité *(4 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 7.1 | Journalisation structurée | 2 | structlog, champs obligatoires, **test de non-fuite de données personnelles** |
| 7.2 | Traçage OpenTelemetry | 1 | Instrumentation FastAPI et SQLAlchemy |
| 7.3 | Métriques Prometheus | 1 | RED sur l'API, exposition `/metrics` |

**Point d'attention 7.1** : le test de non-fuite rejoue un échantillon de journaux
contre une liste de motifs interdits (e-mails, jetons, contenu). Il doit exister avant
qu'il y ait du contenu à fuiter.

### EPIC 8 — Client Flutter *(5 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 8.1 | Projet Flutter, structure feature-first | 2 | Arborescence de `Architecture.md` §6.2 |
| 8.2 | Client HTTP, intercepteurs, gestion des jetons | 2 | Rafraîchissement transparent, mapping d'erreurs |
| 8.3 | Écran de connexion par lien magique | 1 | Parcours complet jusqu'au jeton |

### EPIC 9 — Infrastructure *(4 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 9.1 | Terraform : réseau, cluster, base, Redis | 3 | Environnement staging uniquement |
| 9.2 | Chart Helm pour l'API | 1 | Sans autoscaling à ce stade |

---

## 4. Récapitulatif et engagement

| Epic | Points |
| --- | --- |
| 1 — Socle du dépôt | 5 |
| 2 — Base de données | 11 |
| 3 — Sécurité de la base | 8 |
| 4 — Squelette API | 7 |
| 5 — Authentification | 6 |
| 6 — CI/CD | 6 |
| 7 — Observabilité | 4 |
| 8 — Client Flutter | 5 |
| 9 — Infrastructure | 4 |
| **Total** | **56** |

**Capacité estimée : 34 points. Le backlog en compte 56.**

Cet écart est délibérément exposé plutôt que masqué par une réduction artificielle
des estimations. Deux options, à trancher en planification :

| Option | Effet |
| --- | --- |
| **A — Reporter les epics 8 et 9** (9 points) | Le client et l'infrastructure staging glissent au sprint 2. Reste 47 points : toujours au-dessus. |
| **B — Étendre le sprint 1 à 3 semaines** | Reconnaît que le socle initial n'entre pas dans un sprint standard. |
| **C — Réduire l'epic 2** au périmètre v0.1 (identité, capture, connaissance) | Économise 3 points, mais fragmente le schéma — contraire à la décision de séquencement. |

**Recommandation** : option B. Un sprint de fondation compressé produit des
raccourcis sur la RLS et la CI, précisément les deux éléments dont la correction
ultérieure coûte le plus cher. La vélocité réelle mesurée à la fin remplacera
l'hypothèse de 34 points.

---

## 5. Définition de « terminé »

Une tâche n'est terminée que si **tous** ces points sont vrais :

- [ ] Le code passe ruff, mypy strict et import-linter
- [ ] Les tests unitaires couvrent le comportement, pas seulement les lignes
- [ ] Les tests d'intégration tournent contre un PostgreSQL réel
- [ ] La migration a un `downgrade` testé à l'aller et au retour
- [ ] La documentation concernée dans `/docs` est à jour dans la même PR
- [ ] Aucune donnée personnelle n'apparaît dans les journaux
- [ ] La PR a été revue par une personne qui n'est pas l'auteur
- [ ] La CI est verte

**Règle de documentation** : une PR qui modifie une décision d'architecture sans
mettre à jour `Decisions.md` est refusée. La documentation n'est pas un livrable de
fin de phase, c'est une partie du changement.

---

## 6. Risques du sprint

| # | Risque | Probabilité | Impact | Réponse |
| --- | --- | --- | --- | --- |
| R1 | La RLS prend plus de temps que prévu (pièges de pool de connexions) | Élevée | Élevé | Prototyper 3.3 en premier, sur un jour dédié |
| R2 | Le schéma complet en un sprint est trop ambitieux | Moyenne | Moyen | Ordre : Identité → Capture → Connaissance ; le reste peut glisser |
| R3 | La configuration Terraform bloque sur des quotas ou des droits fournisseur | Moyenne | Faible | Non bloquant pour le sprint 2 ; peut glisser |
| R4 | L'équipe découvre `import-linter` et sur-contraint | Moyenne | Faible | Commencer par 3 contrats, pas 15 |
| R5 | Le test d'isolation multi-locataire révèle des trous tardivement | Faible | **Critique** | L'écrire avant les politiques, pas après |

---

## 7. Dépendances externes

| Dépendance | Nécessaire pour | Action |
| --- | --- | --- |
| Compte fournisseur cloud UE | Epic 9 | À ouvrir avant le début du sprint |
| Fournisseur d'e-mail transactionnel | Epic 5 | Compte de test suffisant |
| Organisation GitHub, runners | Epic 6 | À vérifier : disponibilité des runners macOS |

---

## 8. Ce que le sprint 1 ne prouve pas

Il est important d'être clair sur ce qui reste inconnu à la fin de ce sprint :

- Rien sur la qualité de la transcription ou de l'extraction
- Rien sur la latence réelle du pipeline
- Rien sur le coût unitaire
- Rien sur l'expérience utilisateur

Ces quatre inconnues sont l'objet des sprints 2 et 3.

---

## 9. Revue et rétrospective — points à traiter

| Question | Pourquoi elle compte |
| --- | --- |
| La vélocité réelle par rapport à l'hypothèse de 34 points | Recalibre tout le plan |
| Les contrats d'architecture sont-ils utiles ou pénibles ? | Détermine s'ils survivront |
| Le schéma complet dès le sprint 1 était-il le bon choix ? | Décision structurante à valider ou corriger |
| Combien de temps a réellement pris la RLS ? | Alimente l'estimation des chantiers de sécurité futurs |

---

## Références

- Structure du code → `Architecture.md` §6, §7, §8
- Schéma et RLS → `Database.md` §5, §6
- Erreurs et contrat → `API.md` §6
- CI/CD → `Architecture.md` §13
- Sprint suivant → `Sprint02.md`
