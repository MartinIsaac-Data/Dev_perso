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

Rien pour l'instant. La phase 1 (sprint 01) n'a pas démarré.

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
