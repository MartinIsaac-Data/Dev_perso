# Sprint 02 — Tranche verticale

> **Phase 0 — Conception.** Plan de sprint. Aucun code n'est écrit à ce stade.

| | |
| --- | --- |
| **Sprint** | 02 · Durée 2 semaines |
| **Version cible** | v0.1 — Fondations |
| **Prérequis** | Sprint 01 terminé : schéma, RLS, CI, authentification |
| **Capacité** | À recalibrer sur la vélocité mesurée au sprint 1 |

---

## 1. Objectif du sprint

> **Une capture vocale traverse la chaîne complète — de l'appui sur le bouton
> jusqu'à une tâche affichée dans l'application — sans intervention manuelle.**

C'est la tranche verticale la plus étroite possible qui prouve que l'architecture
tient. Elle traverse toutes les couches : client natif, API, stockage objet, file,
worker, STT, LLM, base, retour au client.

### Critère de réussite unique

Un membre de l'équipe dit « il faut que je rappelle Paul jeudi » dans son téléphone,
et voit apparaître, en moins de 30 secondes, une tâche intitulée « Rappeler Paul »
avec l'échéance du jeudi suivant.

### Ce qui est délibérément grossier à ce stade

| Élément | État au sprint 2 | Traité en |
| --- | --- | --- |
| Un seul chemin d'extraction, sans aiguillage | `claude-opus-5` pour tout | Sprint 3 |
| Un seul élément par capture | Pas de multi-éléments | Sprint 5 |
| Pas de mode hors ligne | Échec si pas de réseau | Sprint 4 |
| Interface minimale | Bouton + liste | Sprints 6 et 9 |
| Résolution temporelle partielle | Jours de semaine et relatif simple | Sprint 5 |
| Pas d'embeddings ni de recherche | — | Sprint 6 |

---

## 2. Backlog

### EPIC 10 — Ingestion de capture *(9 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 10.1 | `POST /v1/captures` | 2 | Création + URL présignée ; idempotence par `client_capture_id` |
| 10.2 | Adaptateur de stockage objet | 2 | Présignature, chiffrement, cycle de vie |
| 10.3 | `POST /v1/captures/{id}/complete` | 1 | Transition d'état + mise en file |
| 10.4 | `GET /v1/captures/{id}` | 1 | Avec transcription et entrées dérivées |
| 10.5 | Machine à états de capture | 2 | Transitions de `Architecture.md` §10.4, invariants testés |
| 10.6 | Test d'idempotence | 1 | Rejeu du POST → même capture, pas de doublon |

**Point d'attention 10.1** : l'idempotence est testée dès maintenant, pas quand le
mode hors ligne arrivera. Elle est la condition de la reprise, et une reprise
construite sur une ingestion non idempotente produit des doublons silencieux.

### EPIC 11 — Traitement asynchrone *(8 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 11.1 | Configuration `arq`, files et priorités | 2 | 4 files de `Architecture.md` §7.3 |
| 11.2 | Orchestrateur de pipeline | 3 | Étapes idempotentes, reprise depuis l'état persisté |
| 11.3 | Politique de reprise et file d'échec | 2 | Backoff exponentiel, jitter, `dead_letter` |
| 11.4 | Dispatcher d'outbox | 1 | Verrou distribué, lecture des événements en attente |

**Point critique 11.2** : chaque étape doit reprendre sans réexécuter les précédentes.
Un échec à l'extraction ne doit pas relancer la transcription, qui est l'opération la
plus coûteuse. C'est la propriété la plus importante du pipeline, et celle qu'un test
doit vérifier explicitement.

### EPIC 12 — Transcription *(9 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 12.1 | Déploiement du service STT | 3 | `faster-whisper large-v3`, GPU, quantification int8_float16 |
| 12.2 | Port et adaptateur `Transcriber` | 2 | Interface abstraite, implémentation locale |
| 12.3 | Prétraitement audio | 2 | Normalisation 16 kHz mono, VAD Silero |
| 12.4 | Garde-fous anti-hallucination | 2 | Seuil de parole, log-probabilité, détection de répétition, liste noire |

**Point d'attention 12.4** : les garde-fous sont livrés en même temps que la
transcription, pas après. Une hallucination Whisper produit un texte parfaitement
formé et entièrement inventé — c'est le mode de défaillance le plus dangereux du
produit et il ne doit jamais atteindre la production.

### EPIC 13 — Extraction *(10 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 13.1 | Port et adaptateur `Llm` | 2 | Abstraction fournisseur, gestion des erreurs et refus |
| 13.2 | Schéma JSON d'extraction | 2 | Contrat de `AI.md` §4.2, validation Pydantic stricte |
| 13.3 | Premier prompt d'extraction | 3 | Structure de `AI.md` §4.3, versionné dans `prompt_version` |
| 13.4 | Traçabilité `ai_run` | 1 | Modèle, tokens, coût, latence — sans contenu |
| 13.5 | Gestion des sorties non conformes | 2 | Une nouvelle tentative, puis dégradation en `note` |

**Point d'attention 13.3** : ce prompt sera réécrit plusieurs fois. Ce qui compte au
sprint 2, c'est que le **schéma** soit stable et que le mécanisme de versionnage
fonctionne — pas que le prompt soit optimal.

### EPIC 14 — Résolution temporelle *(6 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 14.1 | Module de résolution — expressions absolues et relatives simples | 3 | « demain », « le 12 juin », « dans 3 jours » |
| 14.2 | Jours de la semaine | 2 | « jeudi », « jeudi prochain » — règle de prochaine occurrence |
| 14.3 | Jeu de tests temporels | 1 | Changements d'heure, années bissextiles, fuseaux non entiers |

**Point d'attention 14.3** : les tests de changement d'heure sont écrits avant le
code. Le bogue de passage à l'heure d'été est silencieux, saisonnier et impossible à
reproduire six mois plus tard.

### EPIC 15 — Publication et entrées *(6 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 15.1 | Création des entrées depuis l'extraction | 2 | `entry` + spécialisation `task` |
| 15.2 | `GET /v1/entries` avec filtres de base | 2 | Type, statut, pagination par curseur |
| 15.3 | `PATCH /v1/entries/{id}` | 2 | Verrouillage optimiste par `If-Match`, `correction_event` |

### EPIC 16 — Client : capture *(11 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 16.1 | Canal natif audio iOS | 3 | Session audio pré-initialisée, gestion des interruptions |
| 16.2 | Canal natif audio Android | 3 | Idem, plus service de premier plan |
| 16.3 | Écran de capture | 2 | Appui long, forme d'onde, minuteur |
| 16.4 | Envoi et suivi | 2 | Présignature, PUT, complete |
| 16.5 | Liste des entrées | 1 | Affichage brut, sans cache local |

**Point d'attention 16.1 et 16.2** : c'est la partie la plus incertaine du sprint.
La latence de 300 ms p95 est un objectif du PRD ; ce sprint doit **mesurer** la
latence réelle, pas nécessairement l'atteindre. Si elle est de 800 ms, il vaut mieux
le savoir maintenant.

### EPIC 17 — Retour de progression *(4 points)*

| # | Tâche | Points | Détail |
| --- | --- | --- | --- |
| 17.1 | `GET /v1/events/stream` (SSE) | 2 | Événements de `API.md` §10.2 |
| 17.2 | Consommation SSE côté client | 2 | Affichage progressif de la transcription |

---

## 3. Récapitulatif

| Epic | Points |
| --- | --- |
| 10 — Ingestion | 9 |
| 11 — Traitement asynchrone | 8 |
| 12 — Transcription | 9 |
| 13 — Extraction | 10 |
| 14 — Résolution temporelle | 6 |
| 15 — Publication | 6 |
| 16 — Client : capture | 11 |
| 17 — Progression | 4 |
| **Total** | **63** |

Ce total dépasse à nouveau une capacité de sprint standard. Ordre de priorité en cas
de dépassement :

| Priorité | Epics | Justification |
| --- | --- | --- |
| **Indispensable** | 10, 11, 12, 13, 15 | Sans eux, il n'y a pas de tranche verticale |
| **Important** | 16 | Sans client, la démonstration se fait par API — acceptable mais moins probante |
| **Peut glisser** | 14 (partiellement), 17 | Une date non résolue laisse une tâche sans échéance : dégradation acceptable |

---

## 4. Mesures à produire

Ce sprint est le premier à produire des chiffres. Ils sont plus importants que les
fonctionnalités livrées.

| Mesure | Comment | Pourquoi |
| --- | --- | --- |
| Latence tap → enregistrement | Instrumentation client, 100 essais par plateforme | Objectif PRD de 300 ms — validé ou non |
| Latence de bout en bout | Trace complète, p50 et p95 sur 200 captures | Objectif de 25 s p95 |
| Répartition du temps par étape | Traces OpenTelemetry | Identifie le vrai goulot d'étranglement |
| Coût par capture | Somme des `ai_run` | Premier point de comparaison avec l'objectif de 0,004 € |
| Taux d'échec par étape | Compteurs | Où la chaîne casse en pratique |
| WER approximatif | 30 captures transcrites à la main | Première mesure de qualité STT |

**Ces mesures alimentent directement l'arbitrage du sprint 3** (voir `AI.md` §7.3 et
`Decisions.md` ADR-019).

---

## 5. Définition de « terminé » — additions au sprint 1

En plus des critères du sprint 1 :

- [ ] Chaque étape du pipeline est idempotente et testée comme telle
- [ ] Un échec simulé à chaque étape laisse la capture dans un état terminal valide
- [ ] Aucun contenu de transcription n'apparaît dans les journaux ni dans `ai_run`
- [ ] Chaque appel de modèle produit une ligne `ai_run` avec son coût
- [ ] Le module temporel a une couverture ≥ 95 %

---

## 6. Risques du sprint

| # | Risque | Probabilité | Impact | Réponse |
| --- | --- | --- | --- | --- |
| R6 | Le déploiement GPU prend plus de temps que prévu | Élevée | Élevé | Démarrer 12.1 le premier jour ; repli sur API SaaS temporaire pour ne pas bloquer 13.x |
| R7 | La latence de capture dépasse largement 300 ms | Moyenne | Élevé | Mesurer tôt ; si l'écart est structurel, remettre en cause ADR-002 |
| R8 | Le prompt d'extraction donne des résultats médiocres | Élevée | Moyen | Attendu — c'est l'objet du sprint 3, pas un échec |
| R9 | Whisper hallucine sur les captures courtes | Élevée | Élevé | Les garde-fous 12.4 sont prioritaires, pas optionnels |
| R10 | Le coût mesuré dépasse largement l'estimation | Moyenne | Élevé | Ne pas optimiser dans l'urgence ; documenter et arbitrer au sprint 3 |
| R11 | Le canal natif audio diffère trop entre iOS et Android | Moyenne | Moyen | Abstraction Dart commune définie avant les deux implémentations |

---

## 7. Démonstration de fin de sprint

La revue de sprint consiste en une seule démonstration, faite sur un téléphone réel,
sans filet :

1. Ouvrir l'application, appuyer sur le bouton
2. Dire : « Il faut que je rappelle Paul jeudi pour le devis »
3. Relâcher
4. Attendre, en montrant la transcription qui arrive en flux
5. Voir la tâche apparaître avec son échéance

Puis, immédiatement après, une seconde démonstration :

6. Couper le service LLM
7. Refaire une capture
8. Montrer que l'audio et la transcription sont conservés, que l'entrée existe en
   état dégradé, et qu'aucune donnée n'est perdue

La seconde démonstration est aussi importante que la première.

---

## Références

- Séquence complète → `Architecture.md` §4.1
- États du pipeline → `Architecture.md` §10.4
- Contrat d'extraction → `AI.md` §4.2
- Résolution temporelle → `AI.md` §5.1
- Sprint précédent → `Sprint01.md` · Sprint suivant → `Sprint03.md`
