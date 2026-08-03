# MindFlow AI — Feuille de route

> **Phase 0 — Conception.** Cette feuille de route décrit une trajectoire, pas un
> engagement de dates. Les jalons sont ordonnés par dépendance et par apprentissage :
> chaque version doit répondre à une question avant que la suivante ne commence.

| | |
| --- | --- |
| **Version du document** | 0.1 — Phase 0 |
| **Horizon** | v0.1 (interne) → v3.0 |
| **Unité de temps** | Sprints de 2 semaines, équipe de 4 à 6 personnes |

---

## Table des matières

1. [Principe directeur](#1-principe-directeur)
2. [Vue d'ensemble](#2-vue-densemble)
3. [v0.1 — Fondations](#3-v01--fondations-interne)
4. [v0.5 — Boucle complète](#4-v05--boucle-complète-alpha-fermée)
5. [v1.0 — MVP public](#5-v10--mvp-public)
6. [v1.1 — Réunions](#6-v11--réunions)
7. [v1.2 — Intégrations et qualité](#7-v12--intégrations-et-qualité)
8. [v2.0 — Collaboration](#8-v20--collaboration)
9. [v2.5 — Assistant](#9-v25--assistant)
10. [v3.0 — Traitement local](#10-v30--traitement-local)
11. [Chantiers transverses](#11-chantiers-transverses-permanents)
12. [Ce qui pourrait tout changer](#12-ce-qui-pourrait-tout-changer)

---

## 1. Principe directeur

**Chaque version répond à une question, et on ne passe pas à la suivante sans réponse.**

| Version | Question | Critère de réponse |
| --- | --- | --- |
| v0.1 | Le pipeline tient-il debout techniquement ? | Une capture traverse la chaîne de bout en bout |
| v0.5 | La structuration est-elle assez juste pour être utile ? | ≥ 80 % de justesse sur le jeu d'évaluation |
| v1.0 | Les gens reviennent-ils ? | ≥ 40 % de rétention S4/S1 |
| v1.1 | Les réunions justifient-elles un abonnement ? | ≥ 4 % de conversion Free → Pro |
| v1.2 | Le corpus a-t-il de la valeur dans la durée ? | ≥ 50 % d'utilisateurs cherchant en S4 |
| v2.0 | L'usage en équipe existe-t-il ? | ≥ 15 comptes Business payants |
| v2.5 | Le produit devient-il un interlocuteur ? | Engagement conversationnel mesuré |
| v3.0 | Peut-on tenir la promesse de confidentialité totale ? | Traitement local viable |

Une réponse négative n'arrête pas le produit : elle réoriente la version suivante.
Les branches alternatives sont indiquées à chaque jalon.

---

## 2. Vue d'ensemble

```
Sprint  1─2─3─4─5─6─7─8─9─10─11─12─13─14─16─18─20─22─24─────30─────40
        │     │       │         │           │      │        │      │
        ▼     ▼       ▼         ▼           ▼      ▼        ▼      ▼
      v0.1  v0.5    v1.0      v1.1        v1.2   v2.0     v2.5   v3.0
   Fondations Boucle  MVP    Réunions  Intégra-  Collabo- Assis- Local
              complète public          tions     ration    tant
              (alpha)         │
                              └─ premier revenu
```

| Version | Sprints | Livraison | Public | Objectif principal |
| --- | --- | --- | --- | --- |
| **v0.1** | 1–3 | Interne | Équipe | Pipeline de bout en bout |
| **v0.5** | 4–6 | Alpha fermée | ~30 testeurs | Qualité d'extraction |
| **v1.0** | 7–9 | Public | Ouvert | Rétention |
| **v1.1** | 10–13 | Public | Ouvert | Monétisation |
| **v1.2** | 14–17 | Public | Ouvert | Valeur du corpus |
| **v2.0** | 18–24 | Public | + Business | Nouveau segment |
| **v2.5** | 25–32 | Public | Ouvert | Profondeur d'usage |
| **v3.0** | 33–42 | Public | Ouvert | Confidentialité |

---

## 3. v0.1 — Fondations *(interne)*

**Sprints 1 à 3 · Question : le pipeline tient-il debout ?**

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Infrastructure | Dépôt, Docker, CI, environnements local et staging |
| Base | Schéma complet, migrations, RLS, jeux de données de test |
| API | Authentification, captures, entrées — CRUD minimal |
| Pipeline | Ingestion → STT → extraction → publication, un seul chemin |
| Client | Capture, envoi, liste — sans hors ligne, sans widget |
| IA | Jeu d'évaluation initial (150 cas), premier prompt d'extraction |
| Observabilité | Journaux structurés, traces, tableau de bord de santé |

### Critères de sortie

- [ ] Une capture de 15 s produit une tâche correcte, de bout en bout, en < 30 s
- [ ] Le test d'isolation RLS passe sur toutes les tables
- [ ] Le pipeline CI est vert et bloque sur lint, types, architecture et tests
- [ ] Le jeu d'évaluation s'exécute en CI et publie un rapport
- [ ] Un incident sur le LLM ne perd aucune capture

### Ce qui est explicitement absent

Hors ligne, widgets, recherche sémantique, réunions, facturation, notifications.

---

## 4. v0.5 — Boucle complète *(alpha fermée)*

**Sprints 4 à 6 · Question : la structuration est-elle assez juste ?**

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Capture | Mode hors ligne complet, file locale, reprise, idempotence |
| Extraction | Aiguillage par complexité, multi-éléments, résolution temporelle |
| Connaissance | Projets, tags, liens, transformation d'entrée |
| Recherche | Lexicale + sémantique hybride (sans mode `answer`) |
| Correction | Inbox, `needs_review`, correction en ≤ 2 gestes, `correction_event` |
| Client | Synchronisation delta, résolution de conflits, cache local |
| IA | Jeu d'évaluation à 300 cas, calibration de confiance, seuils |

### Critères de sortie

- [ ] Justesse de classification ≥ 80 % sur le jeu d'évaluation
- [ ] Justesse des dates ≥ 88 %
- [ ] Zéro capture perdue sur 2 semaines d'usage interne intensif
- [ ] 30 testeurs recrutés, 10 utilisant le produit quotidiennement
- [ ] Coût unitaire mesuré et documenté (pas nécessairement optimisé)

### Branche alternative

Si la justesse plafonne sous 75 %, la v1.0 est repoussée et un sprint entier est
consacré au prompt et au jeu d'évaluation. Sortir un produit qui se trompe une fois
sur quatre détruirait la première impression, qui ne se rejoue pas.

---

## 5. v1.0 — MVP public

**Sprints 7 à 9 · Question : les gens reviennent-ils ?**

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Capture | Widgets iOS et Android, raccourci vocal système |
| Rappels | Notifications locales et push, revue quotidienne |
| Recherche | Mode `answer` avec citations vérifiées |
| Onboarding | Parcours sans compte jusqu'à la première capture traitée |
| Facturation | Plans Free et Pro, quotas, portail Stripe |
| Conformité | Export complet, suppression de compte, politique de confidentialité |
| Web | Consultation et édition (pas de capture) |
| Qualité | Accessibilité WCAG 2.2 AA, FR + EN |

### Critères de sortie

- [ ] Rétention S4/S1 ≥ 40 % sur la cohorte d'ouverture
- [ ] Activation (3 captures en 7 jours) ≥ 35 %
- [ ] Latence de capture ≤ 300 ms p95, mesurée sur appareils réels
- [ ] Publication ≤ 25 s p95
- [ ] Zéro capture perdue
- [ ] Justesse de classification ≥ 85 %
- [ ] Disponibilité ≥ 99,5 % sur 4 semaines

### Branche alternative

Si la rétention est comprise entre 25 et 40 %, la v1.1 est remplacée par un sprint
d'analyse qualitative : entretiens, enregistrements de session, identification du
point de décrochage. Sous 25 %, l'hypothèse produit centrale est remise en cause et
il faut réinterroger les personas.

---

## 6. v1.1 — Réunions

**Sprints 10 à 13 · Question : les réunions justifient-elles un abonnement ?**

C'est la version qui doit transformer un usage sympathique en dépense assumée. Le
compte-rendu de réunion est la fonctionnalité au ratio valeur/coût le plus favorable
pour les personas Léa et Karim.

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Réunions | Enregistrement long, transcription en flux, synthèse structurée |
| Diarisation | Distinction des locuteurs, attribution proposée des actions |
| Décisions | Suivi de décision, relance à échéance de révision |
| Partage | Lien à durée limitée, export PDF et e-mail |
| Synthèses | Récapitulatif hebdomadaire |
| Wearables | Applications Apple Watch et Wear OS |
| Performance | Optimisation du coût unitaire (aiguillage, cache) |

### Critères de sortie

- [ ] Conversion Free → Pro ≥ 4 % à 90 jours
- [ ] Une réunion de 45 min produit son compte-rendu en ≤ 90 s après la fin
- [ ] Justesse des actions extraites ≥ 85 % sur un corpus de réunions annotées
- [ ] Coût unitaire ≤ 0,010 € par capture courte
- [ ] Le partage est utilisé par ≥ 25 % des utilisateurs Pro

### Branche alternative

Si la conversion reste sous 2 %, le problème n'est pas la fonctionnalité mais le
placement de la barrière payante. La v1.2 testerait alors un modèle différent :
essai de 14 jours sans limite, ou tarification à l'usage.

---

## 7. v1.2 — Intégrations et qualité

**Sprints 14 à 17 · Question : le corpus a-t-il de la valeur dans la durée ?**

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Intégrations | Todoist, Google Tasks, Google Calendar, Notion, Slack |
| Recherche | Reclassement amélioré, détection de thèmes récurrents |
| Liens | Détection de contradiction entre décisions, suggestions de rapprochement |
| Vocabulaire | Amorce contextuelle STT, lexique personnel |
| Langues | Espagnol, allemand, italien |
| Fiabilité | Second fournisseur LLM en repli, tests de chaos |
| Qualité | Réduction du taux de correction sous 12 % |

### Critères de sortie

- [ ] ≥ 50 % des utilisateurs actifs en S4 ont fait au moins une recherche
- [ ] ≥ 30 % des utilisateurs Pro ont connecté une intégration
- [ ] WER sur noms propres amélioré de ≥ 30 % avec l'amorce contextuelle
- [ ] Rappel RAG ≥ 88 %
- [ ] Une panne complète du fournisseur LLM principal reste transparente

---

## 8. v2.0 — Collaboration

**Sprints 18 à 24 · Question : l'usage en équipe existe-t-il ?**

C'est le changement de nature le plus important de la trajectoire : un produit
individuel devient un produit d'équipe. Il introduit un modèle de permissions, une
facturation par siège, et rouvre entièrement le chapitre sécurité (`AI.md` §9.1 :
l'injection de prompt devient un risque réel dès qu'un contenu est partagé).

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Espaces | Espaces partagés, permissions par rôle |
| Attribution | Actions assignées à des utilisateurs réels, notifiées |
| Entreprise | SSO SAML/OIDC, SCIM, journal d'audit exportable |
| Conformité | Rétention configurable, résidence des données UE/US |
| API | API publique, webhooks sortants |
| Sécurité | Reprise complète du modèle de menaces en contexte partagé |

### Critères de sortie

- [ ] ≥ 15 comptes Business payants
- [ ] Aucune fuite inter-espaces sur le test d'isolation étendu
- [ ] Test d'intrusion externe passé sans vulnérabilité critique
- [ ] Le modèle de permissions est compréhensible sans documentation

### Préalable non négociable

Le chapitre 9 de `AI.md` doit être entièrement réécrit et validé **avant** le premier
espace partagé. Un contenu dicté par une personne et traité dans le contexte d'une
autre est un vecteur d'injection que le MVP n'a pas à considérer.

---

## 9. v2.5 — Assistant

**Sprints 25 à 32 · Question : le produit devient-il un interlocuteur ?**

### Périmètre

| Domaine | Contenu |
| --- | --- |
| Conversation | Interrogation multi-tours du corpus, avec mémoire de conversation |
| Actions | L'assistant peut proposer des actions ; **exécution après confirmation explicite** |
| Proactivité | Suggestions contextuelles : « vous n'avez pas suivi cette décision » |
| Synthèses | Bilan mensuel et trimestriel, détection de tendances |
| Vocal | Réponse vocale, mode conversationnel mains libres |

### Critères de sortie

- [ ] ≥ 20 % des utilisateurs Pro utilisent l'assistant chaque semaine
- [ ] Justesse factuelle des réponses ≥ 92 % sur un corpus de questions annotées
- [ ] Zéro action exécutée sans confirmation
- [ ] Coût par conversation maîtrisé et facturé

### Risque principal

Donner une capacité d'action au modèle change la classe de risque : une injection de
prompt réussie ne produit plus une mauvaise extraction, mais une action non voulue.
La confirmation explicite est la contre-mesure minimale et non négociable.

---

## 10. v3.0 — Traitement local

**Sprints 33 à 42 · Question : peut-on tenir la promesse de confidentialité totale ?**

C'est la réponse à ADR-012 et la seule voie vers un chiffrement de bout en bout
crédible.

### Périmètre

| Domaine | Contenu |
| --- | --- |
| STT local | Transcription sur appareil pour les captures courtes |
| Extraction locale | Modèle embarqué pour la classification et l'extraction simple |
| Mode privé | Captures marquées « locale uniquement », jamais envoyées |
| Chiffrement | Chiffrement de bout en bout pour le mode privé |
| Hybride | Bascule automatique local/serveur selon la complexité et le réglage |
| Hors ligne | Produit pleinement utilisable sans réseau |

### Critères de sortie

- [ ] STT local avec un WER ≤ 12 % sur captures courtes en français
- [ ] Extraction locale avec ≥ 75 % de justesse sur la voie triviale
- [ ] Impact batterie ≤ 3 % par jour d'usage normal
- [ ] Le mode privé est vérifiable : aucun trafic réseau lié au contenu

### Dépendance externe

Cette version dépend de la maturité des modèles embarqués et des accélérateurs
matériels mobiles. Elle est positionnée à long terme précisément parce qu'elle
dépend de facteurs hors de notre contrôle. Le calendrier est indicatif.

---

## 11. Chantiers transverses permanents

Ces chantiers ne sont pas des versions : ils avancent à chaque sprint et consomment
une part fixe de la capacité.

| Chantier | Part de capacité | Contenu |
| --- | --- | --- |
| **Qualité IA** | ~15 % | Enrichissement du jeu d'évaluation, itération sur les prompts, calibration |
| **Coût** | ~5 % | Mesure, aiguillage, cache, optimisation continue |
| **Dette technique** | ~10 % | Refactoring, mise à jour de dépendances, nettoyage |
| **Sécurité** | ~5 % | Vulnérabilités, revues, tests d'intrusion, conformité |
| **Accessibilité** | ~5 % | WCAG, lecteurs d'écran, tailles de police, contraste |
| **Support et retours** | ~10 % | Bugs remontés, entretiens utilisateurs, analyse |

**Total transverse : ~50 %.** Ce n'est pas une erreur. Une équipe qui planifie 100 %
de sa capacité en fonctionnalités ne livre ni les fonctionnalités, ni la qualité.

---

## 12. Ce qui pourrait tout changer

Scénarios à faible probabilité mais fort impact, à surveiller.

| Scénario | Probabilité | Impact | Réaction préparée |
| --- | --- | --- | --- |
| Apple ou Google intègre une capture structurée native | Moyenne | **Critique** | Se différencier par le corpus interrogeable et le multi-plateforme, pas par la capture |
| Effondrement du coût des LLM (×10 à la baisse) | Moyenne | Fort, positif | Toute la matrice d'arbitrage de `AI.md` §7.3 devient caduque ; monter en qualité |
| Modèle embarqué de qualité serveur | Moyenne | Fort, positif | Accélérer la v3.0, en faire l'argument central |
| Le fournisseur LLM devient indisponible ou change ses conditions | Faible | **Critique** | ADR-008 prévoit l'abstraction ; le second fournisseur est en v1.2 |
| Réglementation européenne durcissant le traitement vocal | Faible | Fort | L'hébergement UE (ADR-024) et la v3.0 sont déjà des réponses partielles |
| Un concurrent lève massivement sur le même positionnement | Moyenne | Moyen | La différenciation est dans la qualité d'extraction, qui ne s'achète pas |

---

## Références

- Périmètre et fonctionnalités → `PRD.md`
- Architecture → `Architecture.md`
- Décisions → `Decisions.md`
- Détail des premiers sprints → `Sprint01.md`, `Sprint02.md`, `Sprint03.md`
- Suivi → `Changelog.md`, `TODO.md`


---

## État réel au 3 août 2026

| Version | Question à laquelle elle répond | État |
| --- | --- | --- |
| v0.1 | « Peut-on capturer une pensée sans y penser ? » | ✅ Phase 1 |
| v0.2 | « Ce qui en sort est-il exploitable ? » | ✅ Phase 1 |
| v0.3 | « Peut-on planifier, retrouver et mesurer ? » | ✅ **Phase 2** |
| v0.4 | « L'extraction s'améliore-t-elle, et le sait-on ? » | ⏳ Bloquée par le corpus d'évaluation (E2) |
| v0.5 | « Le produit tient-il sur plusieurs appareils ? » | ⏳ Bloquée par E6 |

**Ce que la phase 2 a changé à la trajectoire.** Deux choses, et aucune n'était
prévue :

1. La phase 2 rend le taux de correction **visible** sur le tableau de bord. Ce
   chiffre était jusqu'ici une abstraction ; il devient une pression. Mais sans
   corpus annoté (E2), on le regarde bouger sans savoir pourquoi — ce qui déplace
   E2 de « souhaitable » à « bloquant pour v0.4 ».
2. Les appareils sont maintenant réellement enregistrés, plusieurs par compte.
   La synchronisation multi-appareils cesse d'être théorique : deux appareils qui
   modifient la même tâche hors ligne divergeront, et rien ne le résout
   aujourd'hui (E6).
