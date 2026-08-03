# MindFlow AI — Feuille de route V2

| | |
| --- | --- |
| **Version du document** | 1.0 — écrite à la fin de la phase 4 |
| **Point de départ** | 0.5.0 : le produit fait ce qui était prévu, et n'a jamais tourné en production |
| **Horizon** | Les douze mois qui suivent la première mise en production réelle |
| **Complément** | `RoadmapV3.md` pour ce qui vient après, `Roadmap.md` pour la trajectoire d'origine |

> **Cette feuille de route commence par un aveu.** Quatre phases ont produit un
> système complet, testé à 777 tests, et **jamais déployé**. Aucun appel à un
> vrai fournisseur d'IA n'a été passé, aucune synchronisation réelle n'a eu
> lieu, aucune restauration de sauvegarde n'a été testée, aucune charge n'a été
> mesurée. La V2 n'est donc pas « la suite des fonctionnalités » : c'est le
> moment où l'on découvre lesquelles de nos hypothèses étaient fausses.

---

## 1. Le principe qui gouverne la V2

**Rien de neuf tant que l'existant n'est pas mesuré.**

C'est inhabituel pour une feuille de route, et c'est délibéré. Quatre phases ont
ajouté ; la cinquième doit apprendre. Un produit qui empile des fonctionnalités
non mesurées finit par ne plus savoir laquelle réparer quand quelque chose ne va
pas — et il y a déjà, dans ce système, six ou sept hypothèses structurantes que
personne n'a jamais confrontées au réel.

| # | Hypothèse en vigueur | Ce qui la confirmerait ou l'infirmerait |
| --- | --- | --- |
| H1 | L'extraction est « assez juste » | Un corpus annoté, et un chiffre |
| H2 | La recherche hybride bat chacun de ses deux moteurs | La même chose, sur des requêtes réelles |
| H3 | La politique restrictive coûte peu | Un `EXPLAIN ANALYZE` sur une organisation de 500 personnes |
| H4 | HNSW tient sous filtre étroit | Une mesure de rappel à corpus mixte |
| H5 | Les conflits de synchronisation sont rares | Le taux réel, une fois branché |
| H6 | Trente jours est la bonne durée de vie d'un lien | La distribution des ouvertures |

**Aucune de ces six lignes ne peut être résolue par du code.** Elles se résolvent
par une mise en production et un instrument de mesure. C'est l'ordre du jour de
la V2.

---

## 2. Vue d'ensemble

```
        │ V2.0 │ V2.1 │ V2.2 │ V2.3 │ V2.4 │
        ▼      ▼      ▼      ▼      ▼
     Produc- Mesure  Temps  Hors  Écheler
      tion           réel   ligne
```

| Jalon | Question à laquelle il répond | On n'y passe pas sans |
| --- | --- | --- |
| **V2.0** | Le système tient-il debout hors du poste de développement ? | Un déploiement, une restauration testée |
| **V2.1** | Ce qu'il produit est-il juste ? | Un corpus annoté et des chiffres publiés en interne |
| **V2.2** | L'IA en réunion tient-elle sa promesse ? | Une réunion réelle transcrite en direct |
| **V2.3** | Le produit est-il utilisable dans un train ? | Une session hors ligne complète, resynchronisée |
| **V2.4** | Tient-il à mille utilisateurs ? | Un test de charge, pas une estimation |

---

## 3. V2.0 — Mettre en production, pour de vrai

**La version la moins spectaculaire et la plus importante.**

| Chantier | Pourquoi il bloque tout le reste |
| --- | --- |
| Manifestes de déploiement | `Deployment.md` décrit un plan que rien n'exécute. Les manifestes n'existent pas |
| Une restauration de sauvegarde **testée** | Une sauvegarde jamais restaurée n'est pas une sauvegarde |
| PgBouncer en mode transaction | Le vrai plafond de montée en charge (`Production.md` §5). Incompatible avec les instructions préparées d'asyncpg sans configuration |
| Alertes câblées sur les six signaux | Les métriques existent ; rien ne les regarde |
| Un vrai fournisseur STT/LLM/embedding | Les faux passent les tests et renvoient du bruit vraisemblable |
| OAuth réel pour les sept intégrations | Les connecteurs sont écrits contre des contrats, jamais contre un serveur |

**Le point le plus risqué est le dernier.** Sept intégrations écrites sans qu'un
seul jeton n'ait été échangé : il faut s'attendre à ce que plusieurs contrats
soient faux — pagination, format de date, sémantique d'`etag`. Le port et les
tests survivront ; les adaptateurs seront réécrits. C'est le prix de les avoir
écrits d'avance, et il était connu.

**Critère de sortie.** Une capture faite depuis un téléphone, sur une
installation déployée, avec un vrai modèle, retrouvée par la recherche
sémantique, et un rappel reçu à l'heure.

---

## 4. V2.1 — Savoir si c'est juste

**Le corpus d'évaluation, dette la plus ancienne du projet** (E2, ouverte en
phase 1, aggravée à chaque phase).

| Livrable | Ce qu'il rend possible |
| --- | --- |
| 500 captures annotées, réparties par type et par langue | Mesurer H1 |
| 200 questions avec réponse attendue et sources attendues | Mesurer H2 et la qualité de l'assistant |
| Un harnais d'évaluation en CI | Empêcher une régression silencieuse de prompt |
| Un tableau de bord de justesse par version de prompt | Relier une baisse à un changement précis |

**Ce que ce chantier va probablement révéler.** Le taux de correction affiché
depuis la phase 2 monte quand l'extraction se dégrade *et* quand les
utilisateurs deviennent plus exigeants. On le regarde bouger sans savoir
pourquoi. Un corpus fixe sépare les deux — et c'est la seule façon de savoir si
un changement de prompt a aidé.

**Pourquoi ceci vient avant toute nouvelle fonctionnalité IA.** Élargir une
couche non mesurée revient à empiler des hypothèses. La phase 3 s'est terminée
sur cette phrase ; la phase 4 ne l'a pas résolue parce qu'elle a construit
ailleurs. Elle ne peut plus être reportée.

---

## 5. V2.2 — L'IA en réunion, en direct

La table `meeting_session` existe depuis la phase 4. **Rien ne la remplit.**

| Chantier | Contenu |
| --- | --- |
| Transcription en flux | WebSocket, fenêtres glissantes, diarisation minimale |
| Extraction incrémentale | Décisions et actions repérées *pendant*, pas après |
| Vue de réunion partagée | Les participants d'un espace voient le même fil se construire |
| Compte rendu à la clôture | Réutilise le prompt de résumé existant, sur un corpus de session |

**La difficulté n'est pas la transcription, c'est la latence acceptable.** Un
compte rendu correct dix secondes après la fin d'une réunion vaut mieux qu'une
suggestion approximative pendant. La conception doit trancher explicitement ; le
défaut sera *tard et juste*.

**La contrainte de coût d'ADR-047 s'applique.** Une réunion d'une heure ne peut
pas déclencher un appel de modèle toutes les dix secondes. Le découpage se fait
sur les silences et les changements de locuteur, pas sur une horloge.

---

## 6. V2.3 — Le mode hors ligne, jusqu'au bout

La capture est déjà hors ligne depuis la phase 1 (ADR-009, ADR-034). **Le reste
ne l'est pas.**

| Ce qui marche déjà hors ligne | Ce qui ne marche pas |
| --- | --- |
| Enregistrer une capture | Consulter ses notes |
| La file locale et son rejeu | Cocher une tâche |
| | Commenter |
| | Chercher |

| Chantier | Décision à prendre |
| --- | --- |
| Miroir local des entrées récentes | Quelle fenêtre : trente jours ? l'espace actif ? |
| File de mutations sortantes | Ordonnée par entité, pas globale |
| Résolution des divergences | **Le même choix qu'en ADR-056** : classer, ne pas trancher |
| Indicateur de fraîcheur | Une donnée périmée doit se dire périmée |

**Deux appareils modifiant la même tâche hors ligne divergeront** — c'est la
dette E6, ouverte en phase 2 et toujours ouverte. La réponse ne doit pas être le
dernier-qui-écrit-gagne, pour la raison exacte donnée en ADR-056 : cela perd
silencieusement la version à laquelle quelqu'un tenait.

---

## 7. V2.4 — Tenir à mille utilisateurs

L'architecture est *conçue* pour des milliers d'utilisateurs. Elle n'a jamais vu
plus de deux.

| Chantier | Ce qu'il attaque |
| --- | --- |
| Test de charge à 1 000 comptes, 50 espaces, 200 000 notes | H3, H4, et tout le reste |
| `EXPLAIN ANALYZE` sur les dix requêtes chaudes | Valider ou casser les index de la phase 4 |
| Worker planifié multi-instance | Le seul composant qui ne s'étend pas horizontalement |
| Réplique de lecture pour l'analytique | `/v1/admin/*` et les statistiques |
| Rétention d'audit automatisée | Aujourd'hui : une fonction SQL que personne n'appelle |

**Le worker planifié est le vrai plafond structurel.** Les jobs qui réclament des
lignes utilisent `FOR UPDATE SKIP LOCKED` et supportent déjà plusieurs
instances ; `ensure_audit_partitions` et les résumés périodiques ne sont pas
protégés de la même façon. Un verrou consultatif par job suffit, et il n'est pas
écrit.

**Ce qui pourrait casser en premier, à mon avis.** La sous-requête `EXISTS` sur
`workspace_member` dans la politique restrictive, sur une organisation de
plusieurs centaines de personnes avec des dizaines d'espaces. L'index la couvre
en théorie ; personne n'a vu le plan.

---

## 8. Ce qui n'est pas dans la V2, et pourquoi

| Écarté | Raison |
| --- | --- |
| Nouvelles intégrations | Sept sont écrites et zéro n'a jamais parlé à un vrai serveur |
| Nouvelles capacités IA | Voir §4 : mesurer avant d'élargir |
| Chiffrement de bout en bout | Incompatible avec la recherche serveur. C'est un sujet de V3 (ADR-012) |
| Multi-région | `account.data_region` existe depuis la phase 1 et n'a jamais servi. Sans utilisateur qui l'exige, c'est de la complexité gratuite |
| Marketplace de connecteurs | Le port existe ; l'ouvrir avant d'avoir stabilisé sept connecteurs internes exporterait nos erreurs |

---

## 9. Les risques de la V2, nommés

| Risque | Probabilité | Ce qu'on fait si ça arrive |
| --- | --- | --- |
| Les adaptateurs d'intégration sont faux en production | **Élevée** | Le port tient, les adaptateurs se réécrivent. Prévoir le temps plutôt que d'espérer |
| La qualité d'extraction mesurée est inférieure à ce qu'on croit | Moyenne | C'est le but de la mesure. Le corpus dira quoi corriger |
| La politique restrictive coûte cher à grande organisation | Moyenne | Vue matérialisée d'appartenance, rafraîchie à l'écriture |
| Le coût des modèles rend le produit non viable | Moyenne | ADR-047 est déjà la réponse structurelle ; l'étendre à d'autres questions |
| Personne n'utilise les espaces | **Faible mais grave** | Toute la phase 4 devient du poids mort. Le mesurer tôt, dès V2.0 |

**Le dernier mérite d'être dit franchement.** La phase 4 a été construite sur
l'hypothèse que l'usage en équipe existe. Cette hypothèse n'a jamais été testée
auprès d'un utilisateur. Si elle est fausse, la bonne réaction n'est pas de
défendre le travail fait mais de le laisser dormir : il ne coûte rien tant que
personne ne crée d'espace, puisqu'une note sans espace reste strictement privée.
