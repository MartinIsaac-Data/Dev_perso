# MindFlow AI — TODO

> État à la clôture de la **phase 0 (conception)**. Ce document recense ce qui reste
> à faire, ce qui reste à décider, et ce qui a été délibérément laissé de côté.
> Il est mis à jour à chaque fin de phase.

**Dernière mise à jour** : 2026-08-02 · Clôture de la phase 0

**Légende de priorité**

| | Signification |
| --- | --- |
| 🔴 | Bloquant — le développement ne doit pas démarrer sans |
| 🟠 | Important — à traiter pendant la phase 1 |
| 🟡 | Souhaitable — à traiter avant l'ouverture publique |
| ⚪ | Différé — consigné pour ne pas être oublié |

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
| Assistant conversationnel multi-tours | La recherche one-shot valide l'hypothèse H3 | v2.5 |
| Traitement local sur appareil | Dépend de la maturité des modèles embarqués | v3.0 |
| API publique | Coût de support avant traction | v2.0 |
| Langues au-delà de FR et EN | Chaque langue est un travail de résolution temporelle | v1.2 |
| Analyse de sentiment, scoring d'utilisateurs | **Ligne rouge éthique** — ne sera pas fait | Jamais |
| Génération de contenu à la place de l'utilisateur | Hors positionnement : le produit structure, il n'invente pas | Jamais |

---

## 7. Actions immédiates

Les cinq choses à faire en premier, dans l'ordre.

| # | Action | Pourquoi en premier |
| --- | --- | --- |
| 1 | Traiter P1, P2, P3 — comptes cloud, accès LLM, contrat de rétention | Bloquent les sprints 1 et 2, avec des délais externes non maîtrisés |
| 2 | Mener 6 à 8 entretiens utilisateurs (D2) | Les personas sont construits, pas observés — c'est le risque produit le plus fondamental |
| 3 | Commencer la constitution du jeu d'évaluation (D13) | La tâche la plus longue et la plus déterminante ; à démarrer en tâche de fond dès maintenant |
| 4 | Prototyper la RLS et le contexte de session (sprint 01, R1) | Le risque technique le plus élevé du premier sprint |
| 5 | Arbitrer la durée du sprint 01 (2 ou 3 semaines) | Le backlog dépasse la capacité de 65 % — voir `Sprint01.md` §4 |

---

## Références

- Décisions et questions ouvertes → `Decisions.md`
- Écarts et compromis → `Changelog.md`
- Trajectoire → `Roadmap.md`
- Plans de sprint → `Sprint01.md`, `Sprint02.md`, `Sprint03.md`
