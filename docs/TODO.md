# MindFlow AI — TODO

> État à la clôture de la **phase 4 (fonctionnalités d'entreprise)**. Ce document recense ce qui reste
> à faire, ce qui reste à décider, et ce qui a été délibérément laissé de côté.
> Il est mis à jour à chaque fin de phase.

**Dernière mise à jour** : 2026-08-03 · Clôture de la phase 4

**Légende de priorité**

| | Signification |
| --- | --- |
| 🔴 | Bloquant — le développement ne doit pas démarrer sans |
| 🟠 | Important — à traiter pendant la phase 1 |
| 🟡 | Souhaitable — à traiter avant l'ouverture publique |
| ⚪ | Différé — consigné pour ne pas être oublié |

---

## 0. Dette ouverte par la phase 2

| # | Élément | Priorité | Pourquoi maintenant |
| --- | --- | --- | --- |
| E1 | Reprise automatique du mode dégradé | 🔴 | Reportée depuis la phase 1. Une capture traitée quota atteint n'est **jamais** reprise : le report est en pratique un abandon |
| E2 | Corpus d'évaluation annoté (AI.md §7) | 🔴 | La phase 2 mesure le taux de correction ; sans corpus on ne sait toujours pas si une modification de prompt l'améliore |
| E3 | Pagination par curseur exposée au client | 🟠 | La recherche et l'agenda chargent une page fixe. Au-delà de 200 résultats, l'utilisateur ne voit pas le reste |
| E4 | Chemin de notification Windows jamais exécuté sur un vrai poste | 🟠 | Testé par adaptateur et par contrat, jamais de bout en bout : ni MSIX, ni exécutable Windows produit ici |
| E5 | Budget de coût par compte | 🟠 | Le coût IA est désormais **affiché** sur le tableau de bord ; aucun plafond n'est appliqué |
| E6 | Synchronisation multi-appareils (API.md §9) | 🟠 | Plusieurs appareils sont maintenant réellement enregistrés, ce qui rend la divergence possible |
| E7 | RAG pour le rattachement aux projets | 🟠 | Toujours une correspondance floue de libellés |
| E8 | Tests de bout en bout du client | 🟠 | 90 tests couvrent la logique, aucun l'assemblage |
| E9 | Purge des rappels `sent` anciens | 🟡 | La table `reminder` croît sans borne ; rien ne l'élague |
| E10 | Zoom et export du graphe d'activité | ⚪ | Hors périmètre, consigné pour ne pas être redemandé |
| E11 | Traduction de l'interface | ⚪ | Tout est en français en dur, y compris les verbes de la timeline |

---

## 0 bis. Dette ouverte par la phase 1 (état)

Ce que le MVP laisse en l'état, constaté à la livraison plutôt qu'anticipé.

| # | Élément | Priorité | Pourquoi maintenant |
| --- | --- | --- | --- |
| D1 | Corpus d'évaluation annoté (AI.md §7) | 🔴 | Sans lui, toute modification de prompt est un pari. Préalable à Q1 et Q2 |
| D2 | Reprise automatique des captures en mode dégradé | 🔴 | **Toujours ouverte**, reprise en E1 |
| D3 | Budget de coût par compte | 🟠 | Le prix par jeton est instrumenté, aucun plafond n'est appliqué |
| D4 | RAG (AI.md §6) | 🟠 | Le rattachement à un projet repose sur une correspondance floue de libellés ; cela plafonnera |
| D5 | Notifications d'échéance | ✅ | **Faite en phase 2** : rappels, FCM, WNS, programmation locale |
| D6 | Synchronisation multi-appareils (API.md §9) | 🟠 | La file locale ne couvre que « pas encore parti », pas « modifié ailleurs » |
| D7 | Tests de bout en bout du client contre un back-end réel | 🟠 | Les tests actuels couvrent la logique, pas l'assemblage |
| D8 | Pagination par curseur exposée au client | 🟠 | **Toujours ouverte**, reprise en E3 |
| D9 | Purge des fichiers audio orphelins du stockage objet | 🟡 | Une suppression de capture retire la ligne ; un échec de suppression d'objet n'est pas retenté |
| D10 | Exécution locale de `docker compose` | 🟡 | Toujours jamais lancée faute de démon Docker ; seule la CI la valide |
| D11 | Traduction des messages d'erreur | ⚪ | **Toujours ouverte**, reprise en E11 |

---

## 1. Préalables au démarrage du développement

Ces éléments sont à traiter **avant** le sprint 01.

| # | Élément | Priorité | Responsable | Bloque |
| --- | --- | --- | --- | --- |
| P1 | Ouvrir un compte cloud UE avec quota GPU vérifié | 🔴 | Infra | Sprint 01 epic 9, sprint 02 epic 12 |
| P2 | Souscrire l'accès à l'API du fournisseur LLM, vérifier les limites de débit | 🔴 | IA | Sprint 02 epic 13 |
| P3 | Obtenir le contrat sans rétention ni entraînement du fournisseur LLM | 🔴 | Direction | ADR-008, politique de confidentialité |
| P4 | Sélectionner et contractualiser le repli STT | 🟠 | IA | Sprint 03 epic 22 |
| P5 | Enregistrer les comptes développeur Apple et Google Play | 🟠 | Mobile | Distribution, sprint 02 |
| P6 | Rédiger la politique de confidentialité et les CGU | 🟠 | Juridique | Ouverture publique, v1.0 |
| P7 | Réaliser l'analyse d'impact (AIPD) — traitement vocal à grande échelle | 🟠 | Juridique + Archi | Ouverture publique, v1.0 |
| P8 | Constituer le registre des traitements | 🟡 | Juridique | Conformité continue |
| P9 | Recruter 30 testeurs pour l'alpha fermée | 🟡 | Produit | v0.5, sprint 04 |
| P10 | Valider l'hypothèse tarifaire (9 €/mois) par test | 🟡 | Produit | v1.0, question ouverte Q7 |

---

## 2. Décisions ouvertes

Reprises de `Decisions.md` §Décisions non prises. Chacune bloque une phase.

| # | Question | À trancher avant | Donnée manquante | Priorité |
| --- | --- | --- | --- | --- |
| Q1 | Modèle de la voie standard : `claude-opus-5` ou `claude-sonnet-5` | Sprint 03 | Distribution réelle de complexité + écart de qualité mesuré | 🔴 |
| Q2 | Seuil exact de `needs_review` | Sprint 04 | Calibration de la confiance sur données réelles | 🟠 |
| Q3 | `vector(1024)` ou `halfvec(1024)` | v1.1 | Pression mémoire réelle de l'index HNSW | 🟡 |
| Q4 | Modèle de collaboration : espaces partagés ou partage par entrée | v2.0 | Entretiens utilisateurs sur l'usage en équipe | ⚪ |
| Q5 | Mode journal chiffré de bout en bout comme fonctionnalité distincte | v2.0 | Demande réelle mesurée, pas supposée | ⚪ |
| Q6 | Reclassement par cross-encoder dans le RAG | v1.2 | Jeu d'évaluation RAG suffisamment fourni | ⚪ |
| Q7 | Prix réel du palier Pro | Ouverture publique | Tests tarifaires | 🟡 |
| Q8 | Second fournisseur LLM pour la redondance | v1.2 | Coût de l'abstraction et qualité comparée | ⚪ |

---

## 3. Dette de conception

Éléments de la phase 0 qui ne sont pas assez aboutis et qu'il faudra reprendre.

### 3.1 Produit

| # | Dette | Impact | Quand |
| --- | --- | --- | --- |
| D1 | Les hypothèses H1 à H4 du PRD ne sont pas validées | Le produit repose sur des suppositions | v0.5 (alpha) |
| D2 | Aucun entretien utilisateur n'a été mené — les personas sont construits, pas observés | Risque de concevoir pour des personnes qui n'existent pas | Avant le sprint 04 |
| D3 | Le parcours d'onboarding est décrit mais pas testé | Le taux d'activation de 60 % est un objectif sans base | v1.0 |
| D4 | Les wireframes ne couvrent pas les états vides, d'erreur et de chargement | Ces états représentent une part importante de l'expérience réelle | Sprint 06 |
| D5 | Aucune recherche sur la concurrence directe n'est documentée en profondeur | Le positionnement peut être fragile | Avant v1.0 |

### 3.2 Technique

| # | Dette | Impact | Quand |
| --- | --- | --- | --- |
| D6 | La stratégie de migration `expand-migrate-contract` est décrite mais jamais exercée | Le premier changement destructif sera risqué | Sprint 04 |
| D7 | Le modèle de synchronisation client n'a pas été prototypé | C'est la partie la plus complexe du client | Sprint 04 |
| D8 | Le dimensionnement du nœud GPU repose sur des estimations publiques | Le coût peut être significativement différent | Sprint 02 |
| D9 | Aucune stratégie de test de charge n'est définie | On ne saura pas où ça casse avant que ça casse | v1.0 |
| D10 | Les runbooks d'astreinte n'existent pas | Une alerte sans runbook est une alerte inutile | v1.0 |
| D11 | La stratégie de feature flags est mentionnée mais pas spécifiée | Le déploiement canari en dépend | Sprint 03 |
| D12 | Le schéma local Flutter (Drift) n'est pas spécifié | Divergence possible avec le schéma serveur | Sprint 04 |

### 3.3 IA

| # | Dette | Impact | Quand |
| --- | --- | --- | --- |
| D13 | Le jeu d'évaluation n'existe pas | Aucune décision IA n'est fondée sans lui | Sprint 03 — 🔴 |
| D14 | Les prompts ne sont pas rédigés, seule leur structure l'est | Attendu en phase 0, mais c'est le cœur de la qualité | Sprint 02 |
| D15 | Le taux d'hallucination Whisper sur audio court n'est pas mesuré | Mode de défaillance le plus dangereux du produit | Sprint 02 |
| D16 | Le modèle d'embedding n'est pas choisi précisément | Détermine la dimension, donc le schéma | Sprint 03 |
| D17 | Aucune évaluation RAG n'existe (jeu de questions annotées) | Le rappel de 85 % est un objectif sans mesure | Sprint 06 |
| D18 | La stratégie de redaction PII avant envoi au LLM n'est pas spécifiée | Fonctionnalité annoncée dans `AI.md` §10.2 | v1.0 |

### 3.4 Sécurité et conformité

| # | Dette | Impact | Quand |
| --- | --- | --- | --- |
| D19 | Le modèle de menaces STRIDE est abrégé | Certaines menaces peuvent avoir été omises | Avant v1.0 |
| D20 | Aucun test d'intrusion externe n'est planifié précisément | Exigence avant ouverture publique | v1.0 |
| D21 | La procédure de notification de violation (72 h) n'est pas rédigée | Obligation RGPD | Avant v1.0 |
| D22 | Le chiffrement par clé de locataire (KMS) est décrit sans détail opérationnel | Rotation, révocation, reprise après sinistre | Sprint 04 |
| D23 | Le modèle de menaces en contexte partagé n'existe pas | Bloquant absolu pour la v2.0 | Avant v2.0 — 🔴 pour cette phase |

---

## 4. Chantiers documentaires restants

| # | Document manquant | Utilité | Priorité |
| --- | --- | --- | --- |
| T1 | Guide de contribution et conventions de code | Cohérence de l'équipe | 🟠 |
| T2 | Runbooks d'astreinte, un par alerte critique | Une alerte sans runbook ne sert à rien | 🟠 |
| T3 | Guide de style de l'interface (design system) | Cohérence visuelle, accessibilité | 🟡 |
| T4 | Plan de test de charge | Connaître les limites avant de les atteindre | 🟡 |
| T5 | Plan de reprise après sinistre, avec exercice | Une sauvegarde jamais restaurée n'est pas une sauvegarde | 🟡 |
| T6 | Guide de rédaction des prompts et de versionnage | Reproductibilité des expérimentations IA | 🟠 |
| T7 | Documentation d'API destinée aux intégrateurs | Prérequis de l'API publique | ⚪ |
| T8 | Registre des sous-traitants, public | Exigence RGPD et argument de transparence | 🟡 |

---

## 5. Suivi des écarts identifiés

Reprise des écarts consignés dans `Changelog.md`.

| # | Écart | État | Prochaine action |
| --- | --- | --- | --- |
| E1 | Coût unitaire ×2,5 par rapport à l'objectif PRD | Ouvert | Mesurer au sprint 3, puis arbitrer (`AI.md` §7.3) |
| E2 | MVP non rentable à 5 000 utilisateurs actifs | Ouvert, attendu | Suivre la conversion réelle à partir de la v1.1 |
| E3 | Répartition d'aiguillage non mesurée | Ouvert | Instrumentation au sprint 3 (epic 19.1) |
| E4 | Rappel HNSW sous filtre étroit non mesuré | Ouvert | Mesurer au sprint 6 avec la recherche |
| E5 | Latence de capture de 300 ms non vérifiée | Ouvert | Mesurer au sprint 2 (epic 16) |

**Règle** : un écart n'est clos que lorsqu'il est mesuré et que la décision qui en
découle est consignée dans `Decisions.md`. Un écart qu'on cesse de suivre n'est pas
résolu, il est oublié.

---

## 6. Différé volontairement

Ces éléments ne sont pas des oublis. Ils sont écartés du périmètre courant avec une
raison.

| Élément | Raison | Réexamen |
| --- | --- | --- |
| Applications desktop natives | La web app couvre le besoin | Sur demande utilisateur mesurée |
| Diarisation fine des locuteurs | Coûteuse, sans valeur sur une capture de 15 s | v1.1 |
| ~~Assistant conversationnel multi-tours~~ | **Livré en phase 3** — le besoin s'est révélé structurant plutôt que confortable | ✅ |
| Traitement local sur appareil | Dépend de la maturité des modèles embarqués | v3.0 |
| API publique | Coût de support avant traction | v2.0 |
| Langues au-delà de FR et EN | Chaque langue est un travail de résolution temporelle | v1.2 |
| Analyse de sentiment, scoring d'utilisateurs | **Ligne rouge éthique** — ne sera pas fait | Jamais |
| Génération de contenu à la place de l'utilisateur | Hors positionnement : le produit structure, il n'invente pas | Jamais |

---

## 6 bis. Ce que la phase 3 a laissé ouvert

Écrit après coup, pas avant : ce sont les manques réels de la couche IA telle
qu'elle existe, pas ceux qu'on avait anticipés.

| # | Manque | Gravité | Pourquoi il n'a pas été traité |
| --- | --- | --- | --- |
| A1 | **Aucun appel à un vrai fournisseur n'a été passé.** Tous les adaptateurs sont testés contre des réponses simulées | 🔴 Haute | Aucune clé d'API disponible dans l'environnement. Le premier contact réel révélera des écarts de format |
| A2 | **Aucune évaluation quantitative.** Pas de jeu doré, pas de rappel@k mesuré | 🔴 Haute | Même blocage que E2 depuis la phase 0 : il faut un corpus annoté, qui demande des utilisateurs réels |
| A3 | Le modèle peut ne pas citer. Le prompt l'impose, rien ne le force | 🟠 Moyenne | Une vérification des citations demande de parser la prose du modèle. `assistant_uncited_answers_total` mesure le problème sans le corriger |
| A4 | La qualité du repli sur la récence n'est pas mesurée | 🟠 Moyenne | « Résume mes réunions » renvoie les plus récentes ; sur un corpus de deux ans, ce n'est peut-être pas le bon choix |
| A5 | L'extraction d'entités retente indéfiniment les entrées sans entité | 🟡 Basse | Coût assumé de ne pas porter de colonne d'état ; borné par la taille du lot |
| A6 | Aucun test de charge sur la recherche vectorielle | 🟡 Basse | Le rappel HNSW sous filtre étroit (L5) reste théorique tant qu'aucun corpus réel n'existe |
| A7 | La récupération dégradée en mode hors ligne reste non traitée | 🟠 Moyenne | Ouverte depuis la phase 1. Non aggravée par la phase 3, mais toujours là |
| A8 | Docker Compose n'a jamais été exécuté | 🟠 Moyenne | Le démon Docker n'est pas disponible dans l'environnement de développement |

---

## 6 ter. Ce que la phase 4 a laissé ouvert

Écrit après coup. **Quatre de ces lignes portent sur des fonctionnalités
explicitement demandées et non livrées** ; elles sont marquées 🔴 pour cette
raison, indépendamment de leur difficulté.

| # | Manque | Gravité | Pourquoi il n'a pas été traité |
| --- | --- | --- | --- |
| B1 | ~~`partition_job` n'existe pas~~ | ✅ **Fait** | Quotidien à 03:11 et au démarrage du worker, avec rétention désactivée par défaut. 16 tests, dont un qui épingle le comportement PostgreSQL dont tout le reste découle |
| B2 | ~~`sync_job` n'existe pas~~ | ✅ **Fait** | Toutes les 5 minutes, inter-locataires, avec retard exponentiel plafonné à 1 h et abandon après six échecs. 33 tests |
| B3 | ~~IA temps réel en réunion non implémentée~~ | ✅ **Fait** | Domaine pur (recollement, déclenchement, déduplication), deux prompts, service, neuf routes et un écran. 60 tests côté serveur, 14 côté client |
| B4 | **Mode hors ligne incomplet.** La capture l'est sur toutes les plateformes, y compris le web ; le reste ne l'est nulle part | 🟠 Moyenne | Consulter, cocher, commenter et chercher exigent un miroir local et une file de mutations. Dette E6, ouverte depuis la phase 2. Cadré en `RoadmapV2.md` §6 |
| B5 | ~~Aucun écran Flutter d'entreprise~~ | ✅ **Fait** | Espaces, équipe, mentions, intégrations, administration, plus le panneau de commentaires et la feuille de partage sur le détail d'une note. 39 tests |
| B6 | ~~Aucun build Desktop ni Web produit~~ | ⚠️ **Partiel** | Web et Linux compilés et vérifiés. **Windows et macOS restent non compilés** : Flutter édite les liens contre le SDK de la plateforme, il n'y a pas de compilation croisée, et aucun hôte Windows ou macOS n'est disponible ici. Scaffoldés, script de build écrit, matrice CI câblée — jamais exécutée |
| B7 | **Notifications intelligentes** : les types `mention` et `comment` existent, aucune logique de regroupement ni de silence | 🟠 Moyenne | « Intelligent » demande une règle mesurable. Sans usage réel, toute règle serait une supposition |
| B8 | **Aucun appel réel à un fournisseur d'intégration.** Les sept connecteurs sont écrits contre des documentations | 🔴 Haute | Même blocage que A1. Il faut s'attendre à ce que plusieurs adaptateurs soient faux — ADR-057 en assume le coût |
| B9 | **Le worker planifié ne s'étend pas horizontalement.** `ensure_audit_partitions` et les résumés ne sont pas protégés par `SKIP LOCKED` | 🟠 Moyenne | Un verrou consultatif par job suffirait ; non écrit. Vrai plafond structurel, cadré en `RoadmapV2.md` §7 |
| B10 | **Le coût de la politique restrictive n'est pas mesuré** sur une grande organisation | 🟠 Moyenne | L'index la couvre en théorie ; aucun plan d'exécution n'a été examiné. C'est ce qui casserait en premier |
| B11 | **Aucune restauration de sauvegarde testée**, aucun manifeste de déploiement | 🔴 Haute | Le démon Docker est resté indisponible pendant les quatre phases (A8). Une sauvegarde jamais restaurée n'est pas une sauvegarde |
| B12 | **Un seul propriétaire de compte peut tout** — aucune séparation des pouvoirs | 🟡 Basse | Acceptable à cette échelle ; une organisation de plusieurs centaines de personnes exigera une validation à deux |

**B1, B2, B3 et B5 sont traités, B6 à moitié.** Le déséquilibre énoncé plus
haut — une API complète et invisible — est levé, la seule échéance datée du
produit est supprimée, la synchronisation n'attend plus un clic, le client
compile pour le web et pour Linux, et l'IA en réunion existe.

**Ce qui reste de la liste d'origine : B4**, le hors ligne au-delà de la
capture. C'est le dernier chantier de la taille d'une phase, cadré en
`RoadmapV2.md` §6.

**La capture web est réparée** (ADR-061). Le stockage local est passé derrière
deux ports, avec IndexedDB et `localStorage` côté navigateur ; l'application
démarre sans réseau et la file survit à la coupure, vérifié dans un Chromium par
`tool/smoke_web.mjs`.

**Ce qui reste de B4 est le vrai morceau** : consulter, cocher, commenter et
chercher hors ligne. Cela demande un miroir local des notes et une file de
mutations sortantes, pas une couche de stockage — celle-ci existe désormais et
servira de base.

**Quatre défauts trouvés en ouvrant la page, pas en la compilant.** Aucun n'était
visible dans `flutter build`, `flutter analyze` ni les 152 tests : moteur de
rendu chargé depuis un CDN, police chargée depuis un CDN — l'interface
s'affichait **sans aucun texte** —, écran de démarrage jamais retiré, et un codec
audio que Chrome et Firefox refusent. C'est l'argument le plus concret de ce
document en faveur d'une vérification qui exécute le produit.

**Deux nouvelles lignes ouvertes par les builds** :

| # | Manque | Gravité | Pourquoi |
| --- | --- | --- | --- |
| B13 | Aucune signature de code ni notariat | 🟠 Moyenne | Un `.app` non notarié est refusé par Gatekeeper, un `.exe` non signé déclenche SmartScreen. Demande des certificats, donc un budget et une entité juridique |
| B14 | Le jeu `record` est figé à son niveau de 2024 | 🟡 Basse | Le seul jeu de versions cohérent sous Flutter 3.27. Le débloquer demande `record ^7`, qui demande Flutter ≥ 3.44.8 |
| B15 | Le client ne consomme pas `GET /v1/meetings/{id}/stream` | 🟡 Basse | L'écran de réunion reçoit ses suggestions sur la réponse de chaque bloc, ce qui suffit à l'appareil qui enregistre. Le flux SSE existe et sert au second écran, qui n'est pas construit |
| B16 | Les phrases de déclenchement en réunion sont en français uniquement | 🟡 Basse | `_CUE_PHRASES` est une liste française. À traduire en même temps que l'interface (E11) ; en attendant, une réunion en anglais retombe sur le seuil de mots, qui fonctionne mais réagit plus tard |
| B17 | Aucune réunion réelle n'a été transcrite | 🔴 Haute | Le service est testé contre un transcripteur et un modèle scriptés. Ce qu'un vrai fournisseur de parole rend sur une pièce à quatre personnes reste inconnu, et le recollement est réglé sur des chevauchements supposés |

**B8 reste le risque le plus sous-estimé.** `sync_job` déclenche maintenant sept
connecteurs qui n'ont jamais parlé à un vrai serveur. Le job est testé contre un
connecteur bouchon ; ce qu'il déclenchera en production reste inconnu, et
ADR-057 en assume le coût.

**Deux bugs réels ont été trouvés par les tests d'écran**, et méritent d'être
consignés parce qu'aucun des deux n'aurait été vu à la lecture :

1. `ShareSheet.dispose` lisait `ref` après démontage — le nettoyage du jeton en
   clair ne s'exécutait donc jamais, et l'exception était avalée par le
   framework. Corrigé en capturant le contrôleur pendant que le widget est
   vivant.
2. La carte de conflit mettait ses deux choix dans un `Row` : sur un téléphone,
   l'un des deux était rogné. Un conflit avec une seule issue visible est
   exactement ce qu'ADR-056 refuse.

---

## 7. Actions immédiates

Les choses à faire en premier, dans l'ordre.

| # | Action | Pourquoi en premier |
| --- | --- | --- |
| 1 | Traiter P1, P2, P3 — comptes cloud, accès LLM, contrat de rétention | Bloquent les sprints 1 et 2, avec des délais externes non maîtrisés |
| 2 | Mener 6 à 8 entretiens utilisateurs (D2) | Les personas sont construits, pas observés — c'est le risque produit le plus fondamental |
| 3 | Commencer la constitution du jeu d'évaluation (D13) | La tâche la plus longue et la plus déterminante ; à démarrer en tâche de fond dès maintenant |
| 4 | Prototyper la RLS et le contexte de session (sprint 01, R1) | Le risque technique le plus élevé du premier sprint |
| 5 | Arbitrer la durée du sprint 01 (2 ou 3 semaines) | Le backlog dépasse la capacité de 65 % — voir `Sprint01.md` §4 |
| 6 | **Passer un appel réel à chacun des cinq fournisseurs** (A1) | Toute la couche IA repose sur des formats de fil vérifiés uniquement contre des simulations |
| 7 | **Transcrire une vraie réunion** (B17) | Le recollement est réglé sur des chevauchements supposés ; une pièce à quatre personnes dira si les seuils tiennent |
| 8 | **Passer un vrai appel OAuth sur au moins un connecteur** (B8) | `sync_job` déclenche désormais sept adaptateurs écrits contre des documentations ; le premier contact réel dira lesquels sont faux |
| 9 | **Faire tourner la matrice CI desktop une fois** (B6) | Windows et macOS sont écrits et jamais exécutés ; c'est la seule façon de savoir s'ils compilent |

---

## Références

- Décisions et questions ouvertes → `Decisions.md`
- Écarts et compromis → `Changelog.md`
- Trajectoire → `Roadmap.md`, `RoadmapV2.md`, `RoadmapV3.md`
- Plans de sprint → `Sprint01.md`, `Sprint02.md`, `Sprint03.md`
