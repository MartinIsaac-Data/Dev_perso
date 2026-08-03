# Sprint 03 — Boucle démontrable et mesurable

> **Phase 0 — Conception.** Plan de sprint. Aucun code n'est écrit à ce stade.

| | |
| --- | --- |
| **Sprint** | 03 · Durée 2 semaines |
| **Version cible** | v0.1 — Fondations *(clôture)* |
| **Prérequis** | Sprint 02 : la tranche verticale fonctionne et a produit des mesures |
| **Capacité** | Calibrée sur la vélocité réelle des sprints 1 et 2 |

---

## 1. Objectif du sprint

> **La qualité de l'extraction est mesurée, le coût unitaire est connu, et les
> arbitrages techniques ouverts sont tranchés sur la base de chiffres.**

Le sprint 2 a prouvé que la chaîne fonctionne. Le sprint 3 doit prouver qu'elle
fonctionne *assez bien* — et à quel prix. C'est le sprint qui transforme des
hypothèses de conception en décisions fondées.

### Critères de réussite

1. Un jeu d'évaluation de 150 cas s'exécute en CI et bloque toute régression.
2. La justesse de classification est mesurée, avec sa matrice de confusion.
3. Le coût réel par capture est connu et sa décomposition est publiée.
4. La distribution de complexité des captures est mesurée — **c'est la donnée
   manquante d'ADR-019**.
5. Les questions ouvertes Q1 et Q2 de `Decisions.md` sont tranchées ou documentées
   comme non tranchables en l'état.

---

## 2. Backlog

### EPIC 18 — Dispositif d'évaluation *(13 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 18.1 | Constitution du jeu d'évaluation | 5 | 150 captures annotées : 100 FR, 40 EN, 10 mixtes. Enregistrées par l'équipe et des volontaires, jamais issues de données utilisateur |
| 18.2 | Harnais d'exécution | 3 | Exécute le jeu, produit un rapport structuré |
| 18.3 | Métriques par étage | 3 | Justesse de type, complétude, précision, fidélité du `source_span`, justesse temporelle |
| 18.4 | Intégration CI | 2 | Exécution sur toute PR touchant un prompt, un schéma ou un modèle ; comparaison à la référence |

**Point d'attention 18.1** : c'est la tâche la plus longue et la moins gratifiante du
sprint. Elle est aussi celle qui conditionne toutes les décisions suivantes. Un jeu
d'évaluation médiocre produit des mesures rassurantes et fausses.

**Règle** : les captures d'évaluation doivent inclure des cas réalistes et
désagréables — hésitations, phrases inachevées, bruit de fond, code-switching,
formulations ambiguës. Un jeu composé uniquement de phrases claires mesure la qualité
du modèle sur un corpus qui n'existe pas.

### EPIC 19 — Mesure et arbitrage *(10 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 19.1 | Instrumentation de la complexité des captures | 2 | Nombre de mots, marqueurs temporels, nombre d'actions détectées — sur toutes les captures internes |
| 19.2 | Tableau de bord des coûts | 3 | Coût par capture, par modèle, par opération ; projection mensuelle |
| 19.3 | Comparaison de modèles sur le jeu d'évaluation | 3 | `claude-opus-5` vs `claude-sonnet-5` vs `claude-haiku-4-5` sur la voie standard |
| 19.4 | Rapport d'arbitrage | 2 | Document tranchant Q1 : qualité vs coût, avec les chiffres |

**Livrable clé 19.4** : un document court qui répond à la question « quel modèle pour
la voie standard ? » avec, pour chaque option, la justesse mesurée, le coût mesuré, et
une recommandation argumentée. Sans ce document, ADR-019 reste provisoire.

### EPIC 20 — Aiguillage par complexité *(8 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 20.1 | Classifieur d'aiguillage déterministe | 3 | Règles de `AI.md` §4.1 |
| 20.2 | Voie triviale | 3 | Règles + `claude-haiku-4-5` en classification seule |
| 20.3 | Évaluation par voie | 2 | La justesse de la voie triviale ne doit pas s'effondrer |

**Condition d'engagement** : l'epic 20 n'est implémentée que si la mesure 19.1 montre
une part de captures triviales significative. Si elle est de 10 %, l'aiguillage ne
vaut pas sa complexité et l'epic est annulée — c'est un résultat, pas un échec.

### EPIC 21 — Calibration de la confiance *(7 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 21.1 | Mesure de calibration | 3 | Diagramme de fiabilité, erreur de calibration attendue (ECE) |
| 21.2 | Correction post-hoc si nécessaire | 2 | Régression isotonique sur le jeu d'évaluation |
| 21.3 | Détermination du seuil de `needs_review` | 2 | Ajusté pour ~12 % d'entrées en revue — tranche Q2 |

### EPIC 22 — Résilience *(9 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 22.1 | Disjoncteur sur le STT | 3 | Détection, ouverture, demi-ouverture ; repli SaaS |
| 22.2 | Gestion des refus de contenu | 2 | Aucune nouvelle tentative, état `partially_processed`, message neutre |
| 22.3 | Retraitement des captures dégradées | 2 | Tâche périodique, priorité basse |
| 22.4 | Tests de chaos | 2 | Coupure LLM, coupure STT, coupure Redis, base en lecture seule |

**Point d'attention 22.4** : les tests de chaos vérifient les affirmations de
`Architecture.md` §10.5. Chaque ligne du tableau de résilience doit avoir un test qui
la prouve, sinon c'est une intention, pas une garantie.

### EPIC 23 — Inbox et correction *(9 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 23.1 | Écran inbox | 3 | Regroupement par jour, section `à revoir` en tête |
| 23.2 | Correction du type en un geste | 2 | Trois boutons sur une entrée incertaine |
| 23.3 | Édition d'une entrée | 2 | Titre, échéance, projet |
| 23.4 | Enregistrement des corrections | 2 | `correction_event` + `edited_by_user_at` (ADR-027) |

### EPIC 24 — Observabilité de la qualité *(6 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 24.1 | Tableau de bord qualité IA | 3 | Taux de correction, distribution de confiance, violations de schéma, refus |
| 24.2 | Alertes de dégradation | 2 | Seuils de `AI.md` §8.5 |
| 24.3 | Métriques produit | 1 | Captures créées, temps de publication, part `needs_review` |

---

## 3. Récapitulatif

| Epic | Points | Conditionnel |
| --- | --- | --- |
| 18 — Dispositif d'évaluation | 13 | Non |
| 19 — Mesure et arbitrage | 10 | Non |
| 20 — Aiguillage par complexité | 8 | **Oui — dépend de 19.1** |
| 21 — Calibration | 7 | Non |
| 22 — Résilience | 9 | Non |
| 23 — Inbox et correction | 9 | Non |
| 24 — Observabilité qualité | 6 | Non |
| **Total** | **62** | dont 8 conditionnels |

**Priorité en cas de dépassement**

| Priorité | Epics | Justification |
| --- | --- | --- |
| **Indispensable** | 18, 19 | Sans mesure, aucune décision n'est fondée et le sprint n'a pas d'objet |
| **Important** | 21, 22 | La calibration conditionne `needs_review` ; la résilience conditionne la confiance |
| **Peut glisser** | 20, 23, 24 | 20 est conditionnel ; 23 et 24 peuvent démarrer au sprint 4 |

---

## 4. Décisions à prendre pendant le sprint

Ce sprint doit produire des décisions, pas seulement du code.

| # | Décision | Alimentée par | Formalisée dans |
| --- | --- | --- | --- |
| D1 | Modèle de la voie standard : `opus` ou `sonnet` | 19.3, 19.4 | ADR-019 → statut ✅ ou nouvel ADR |
| D2 | Aiguillage par complexité : conserver ou abandonner | 19.1, 20.3 | ADR-019 |
| D3 | Seuil de `needs_review` | 21.1, 21.3 | `Decisions.md` Q2 |
| D4 | Objectif de coût unitaire : maintenir 0,004 € ou réviser | 19.2 | Mise à jour du PRD §8.2 |
| D5 | Repli STT : conserver le double contrat | 22.1, usage mesuré | ADR-007 |

**Règle** : chaque décision est consignée dans `Decisions.md` avec ses chiffres. Une
décision prise sans laisser de trace du raisonnement sera reprise dans six mois par
quelqu'un qui n'a pas les chiffres.

---

## 5. Définition de « terminé » — additions

En plus des critères des sprints 1 et 2 :

- [ ] Toute modification de prompt déclenche l'évaluation en CI
- [ ] Le rapport d'évaluation est publié en commentaire de PR
- [ ] Chaque affirmation de résilience de `Architecture.md` §10.5 a un test de chaos
- [ ] Les décisions D1 à D5 sont tranchées ou explicitement documentées comme
      reportées, avec la donnée manquante identifiée

---

## 6. Risques du sprint

| # | Risque | Probabilité | Impact | Réponse |
| --- | --- | --- | --- | --- |
| R12 | La constitution du jeu d'évaluation prend deux fois le temps prévu | Élevée | Élevé | Commencer dès le sprint 2 en tâche de fond ; 100 cas valent mieux que 0 |
| R13 | La justesse mesurée est très inférieure à l'attendu | Moyenne | Élevé | Résultat légitime : il déclenche un sprint d'itération sur le prompt avant la v0.5 |
| R14 | Le coût réel est très supérieur à l'estimation | Moyenne | Élevé | Ne pas dégrader la qualité dans l'urgence ; réviser l'objectif du PRD si nécessaire |
| R15 | La confiance du modèle est inutilisable (toujours proche de 1) | Moyenne | Moyen | Correction post-hoc (21.2), ou abandon de la confiance au profit de règles |
| R16 | L'équipe optimise le coût avant d'avoir mesuré la qualité | Moyenne | Moyen | Ordre imposé : 18 et 19 avant 20 |

---

## 7. Clôture de la version v0.1

Le sprint 3 clôt la phase de fondations. Conditions de sortie de v0.1 :

- [ ] Une capture traverse la chaîne de bout en bout en moins de 30 s
- [ ] Le test d'isolation RLS passe sur toutes les tables
- [ ] La CI bloque sur lint, types, architecture, tests, sécurité et évaluation
- [ ] Le jeu d'évaluation existe et produit un rapport
- [ ] Un incident sur le LLM ou le STT ne perd aucune capture — **prouvé par test**
- [ ] Le coût unitaire est connu et documenté
- [ ] Les décisions D1 à D5 sont tranchées ou documentées

### Livrables de fin de phase

Conformément au processus de la phase 0, la clôture produit :

| Livrable | Contenu |
| --- | --- |
| Mise à jour de `Decisions.md` | ADR-019 statué, Q1 et Q2 tranchées, nouveaux ADR issus de D1–D5 |
| Mise à jour de `Architecture.md` | Chiffres réels en §15 remplaçant les estimations |
| Mise à jour de `AI.md` | Répartition d'aiguillage mesurée, métriques réelles en §8.2 |
| Mise à jour du `PRD.md` | Objectif de coût révisé si nécessaire |
| Entrée dans `Changelog.md` | Version v0.1 |
| Mise à jour de `TODO.md` | Report des éléments non traités, nouvelles dettes |
| Note de rétrospective | Compromis techniques retenus et améliorations proposées pour v0.5 |

---

## 8. Améliorations proposées pour la phase suivante *(v0.5)*

À affiner avec les chiffres réels du sprint 3. Pistes identifiées dès la conception :

| # | Piste | Motivation | Effort estimé |
| --- | --- | --- | --- |
| A1 | Mode hors ligne complet | Principe fondateur P2 non encore tenu | Élevé |
| A2 | Extraction multi-éléments | Une capture réelle contient souvent 2 ou 3 choses | Moyen |
| A3 | Mise en cache de préfixe de prompt | Levier de coût non exploité au sprint 3 | Faible |
| A4 | Rattachement automatique aux projets | Réduit fortement la correction manuelle | Moyen |
| A5 | Élargissement du jeu d'évaluation à 300 cas | 150 est un plancher, pas une cible | Moyen |
| A6 | Chunking et embeddings | Prérequis de la recherche sémantique | Moyen |
| A7 | Traitement par lots des captures non urgentes | −50 % de coût sur une part du volume | Faible |
| A8 | Diarisation exploratoire | Prépare la v1.1 sans s'y engager | Faible |

**Priorisation recommandée pour la v0.5** : A1 (principe fondateur), A2 et A4
(qualité perçue), A6 (prérequis de la recherche). A3 et A7 si le coût mesuré au
sprint 3 est problématique.

---

## Références

- Dispositif d'évaluation → `AI.md` §8
- Résilience → `Architecture.md` §10.5
- Coûts → `Architecture.md` §15, `AI.md` §7.3
- Questions ouvertes → `Decisions.md` §Décisions non prises
- Sprint précédent → `Sprint02.md`
- Suite de la trajectoire → `Roadmap.md`


---

## Sprint 04 — Planification, recherche et mesure (phase 2, livré)

Consigné ici plutôt que dans un fichier de plus : la liste des documents de
`/docs` est fixée depuis la phase 0, et l'allonger à chaque sprint la rendrait
illisible.

### Objectif

Faire passer le produit de « capturer et consulter » à « capturer, planifier,
retrouver et mesurer ».

### Épopées livrées

| # | Épopée | Definition of Done |
| --- | --- | --- |
| 25 | Agenda et calendrier | Fenêtres correctes au changement d'heure ; retards dans leur propre section ; densité agrégée en base |
| 26 | Gestion avancée des tâches | Sous-tâches ordonnées et idempotentes ; récurrence qui ne dérive pas ; report qui ne déplace pas l'échéance |
| 27 | Rappels et notifications | Rien ne part deux fois ; rien n'est perdu ; une panne de push ne coûte pas la notification |
| 28 | Recherche plein texte et palette | Une grammaire unique ; une requête malformée ne peut pas renvoyer 500 ; les filtres ignorés sont dits |
| 29 | Statistiques | Tout agrégé en SQL ; les chiffres qui dérangent sont affichés |
| 30 | Historique | Survit à la suppression de son sujet ; distinct de l'audit et des corrections IA |
| 31 | Interface | Système de design, coque adaptative, palette ⌘K, optimisations de liste |

### Ce que le sprint a trouvé sans le chercher

Deux défauts silencieux de la phase 1, tous deux corrigés (ADR-041, ADR-042).
Le second est le plus instructif : les travaux inter-tenants ne voyaient **aucune
ligne** depuis le premier jour, parce que le rôle applicatif est `NOBYPASSRLS` par
construction. Aucune erreur, aucun log, aucun test. Il n'a été découvert que
parce qu'un *nouveau* travail inter-tenants — le répartiteur de rappels — avait un
effet visible quand il fonctionnait.

La leçon, consignée : un travail de fond qui ne produit rien d'observable n'a pas
besoin d'un test « qu'il tourne », il a besoin d'un test **qu'il voie quelque
chose**.
