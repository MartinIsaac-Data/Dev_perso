# MindFlow AI — Architecture Decision Records

> **Phase 0 — Conception.** Chaque ADR consigne une décision qui n'allait pas de soi,
> l'alternative écartée, et **le coût accepté**. La dernière rubrique est la plus
> importante : une décision sans coût identifié est une décision mal comprise.

**Format** : *Contexte → Décision → Alternative écartée → Coût accepté → Réexamen.*

| Statut | Signification |
| --- | --- |
| ✅ Acceptée | En vigueur |
| 🔄 À réexaminer | Acceptée, avec un déclencheur de révision identifié |
| ⚠️ Provisoire | Prise sans données suffisantes ; à confirmer par la mesure |
| ❌ Remplacée | Voir l'ADR qui la remplace |

---

## Index

| # | Titre | Statut | Phase |
| --- | --- | --- | --- |
| [001](#adr-001) | Monolithe modulaire plutôt que micro-services | ✅ | 0 |
| [002](#adr-002) | Flutter pour le client multi-plateforme | ✅ | 0 |
| [003](#adr-003) | FastAPI et Python côté serveur | ✅ | 0 |
| [004](#adr-004) | PostgreSQL + pgvector, pas de base vectorielle dédiée | 🔄 | 0 |
| [005](#adr-005) | Isolation multi-locataire par Row Level Security | ✅ | 0 |
| [006](#adr-006) | arq sur Redis plutôt que Celery | ✅ | 0 |
| [007](#adr-007) | STT auto-hébergé avec repli SaaS | 🔄 | 0 |
| [008](#adr-008) | Claude pour l'extraction structurée | 🔄 | 0 |
| [009](#adr-009) | Capture offline-first et idempotence par identifiant client | ✅ | 0 |
| [010](#adr-010) | Table outbox plutôt qu'un bus de messages | ✅ | 0 |
| [011](#adr-011) | Le brut est immuable, les dérivés sont jetables | ✅ | 0 |
| [012](#adr-012) | Pas de chiffrement de bout en bout au MVP | ⚠️ | 0 |
| [013](#adr-013) | Transcription en flux pendant les réunions | ✅ | 0 |
| [014](#adr-014) | Riverpod pour la gestion d'état Flutter | ✅ | 0 |
| [015](#adr-015) | Drift/SQLite comme source de vérité côté client | ✅ | 0 |
| [016](#adr-016) | Code natif pour les widgets et wearables | ✅ | 0 |
| [017](#adr-017) | SQLAlchemy 2 + Alembic + Pydantic v2 | ✅ | 0 |
| [018](#adr-018) | Stockage objet pour l'audio, jamais la base | ✅ | 0 |
| [019](#adr-019) | Aiguillage par complexité avant l'extraction | ⚠️ | 0 |
| [020](#adr-020) | Résolution temporelle déterministe, pas par le LLM | ✅ | 0 |
| [021](#adr-021) | Embeddings auto-hébergés | 🔄 | 0 |
| [022](#adr-022) | Kubernetes managé, Terraform, Helm | ✅ | 0 |
| [023](#adr-023) | GitHub Actions pour la CI/CD | ✅ | 0 |
| [024](#adr-024) | Hébergement dans l'Union européenne par défaut | ✅ | 0 |
| [025](#adr-025) | Un seul appel LLM synchrone : la réponse RAG | ✅ | 0 |
| [026](#adr-026) | Le quota ne bloque jamais une capture | ✅ | 0 |
| [027](#adr-027) | L'édition utilisateur prime toujours sur le retraitement IA | ✅ | 0 |
| [028](#adr-028) | Suppression d'une capture sans cascade par défaut | ✅ | 0 |

---

<a id="adr-001"></a>
## ADR-001 — Monolithe modulaire plutôt que micro-services

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le système comporte des composants aux profils très différents :
une API à faible latence, des workers longs et coûteux, un service GPU. La tentation
est forte de découper en services dès le départ, d'autant que les frontières
semblent évidentes.

Elles ne le sont pas. Nous n'avons encore aucune donnée de production, aucune
connaissance des points de contention réels, et une équipe de trois à six personnes.
Les frontières « évidentes » d'un produit qui n'a jamais tourné sont des hypothèses.

**Décision.** Un monolithe modulaire déployable, découpé en modules aux frontières
explicites (`Architecture.md` §8), avec un plan de traitement asynchrone séparé.
Chaque module expose un contrat public (`api.py`) qui est sa future frontière de
service. Les règles de couplage sont vérifiées automatiquement en CI par
`import-linter`.

**Alternative écartée.** Micro-services dès le premier jour. Rejetée pour trois
raisons cumulatives : (1) le coût opérationnel — traçage distribué, déploiements
coordonnés, cohérence éventuelle — arrive avant tout bénéfice ; (2) le refactoring
d'une frontière mal placée coûte un déplacement de fichiers dans un monolithe, une
migration de données et une saga entre services ; (3) à ce volume, un seul processus
suffit largement.

**Coût accepté.**
- La discipline modulaire ne tient que si elle est outillée. Sans `import-linter`
  bloquant en CI, le monolithe modulaire devient un monolithe tout court en six mois.
- La mise à l'échelle se fait par bloc : monter l'API monte aussi du code qui n'en a
  pas besoin. Acceptable tant que le processus est léger.
- Un bug dans un module peut affecter tout le processus. Atténué par le fait que le
  traitement lourd est déjà séparé.

**Réexamen.** Lorsqu'un des signaux de `Architecture.md` §9.2 apparaît : besoin de
GPU dédié pour la transcription, cycle de déploiement des prompts découplé de l'API,
ou volume de recherche dix fois supérieur aux écritures.

---

<a id="adr-002"></a>
## ADR-002 — Flutter pour le client multi-plateforme

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le produit doit exister sur iOS, Android et web. Les personas sont
répartis entre iPhone (Léa, Marc) et Android (Karim, Sofia). Une équipe réduite ne
peut pas maintenir trois bases de code. L'application, hors capture audio, est
principalement composée de listes, de formulaires et de détails — pas d'un rendu
graphique exigeant.

**Décision.** Flutter, avec des ponts natifs pour trois zones où il n'a pas
d'équivalent viable : la session audio, les widgets d'écran verrouillé, et les
applications de montre (voir ADR-016).

**Alternative écartée.**
- *Natif iOS + Android.* Meilleure intégration système et meilleure latence audio,
  mais deux fois le travail sur tout le reste, pour une équipe qui n'a pas ce budget.
- *React Native.* Écosystème plus large, mais un rendu qui dépend des composants de
  la plateforme, ce qui complique la cohérence visuelle, et un pont JavaScript qui
  ajoute une couche là où on veut de la prévisibilité.

**Coût accepté.**
- Les zones critiques — la capture audio, précisément ce qui doit être le plus
  fiable — passent par du code natif par plateforme. La partie la plus importante du
  produit est donc celle qui bénéficie le moins du choix multi-plateforme.
- Binaire plus lourd (~15 Mo de surcoût), à surveiller face à l'objectif de 60 Mo.
- Le vivier de développeurs Dart est plus étroit que celui de TypeScript ou de Swift.
- Flutter Web reste une cible de seconde classe : l'expérience y sera acceptable,
  pas excellente.

**Réexamen.** Si la latence de capture ne tient pas l'objectif de 300 ms p95 malgré
l'optimisation native, ou si Flutter Web bloque un usage bureau significatif.

---

<a id="adr-003"></a>
## ADR-003 — FastAPI et Python côté serveur

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le cœur de valeur du produit est le pipeline IA : transcription,
extraction, embeddings, évaluation. C'est là que se joue la qualité. Le reste — API
CRUD, authentification, facturation — est du travail standard qu'à peu près
n'importe quel langage fait bien.

**Décision.** Python 3.13 et FastAPI, du contrôleur HTTP jusqu'aux workers, avec
SQLAlchemy 2 en asynchrone.

**Alternative écartée.**
- *Go.* Meilleur débit, meilleure empreinte mémoire, déploiement plus simple. Mais
  l'écosystème IA — SDK, outils d'évaluation, bibliothèques audio, prétraitement —
  vit en Python. Choisir Go imposerait soit de réécrire, soit d'ajouter un service
  Python : deux langages serveur pour une petite équipe.
- *Node.js / NestJS.* Bon écosystème, mais moins outillé pour l'évaluation de
  modèles et le traitement audio.
- *Django.* Beaucoup de fonctionnalités prêtes, mais son ORM synchrone et son modèle
  de requête cadrent mal avec un pipeline massivement asynchrone.

**Coût accepté.**
- Débit brut inférieur à Go d'un facteur significatif. Compensé par le fait que
  l'API ne fait rien de coûteux (ADR-025) et par la mise à l'échelle horizontale.
- Le GIL est un plafond pour les tâches CPU. Le traitement lourd est de toute façon
  déporté sur des workers et sur le service GPU.
- Le typage graduel est plus faible qu'un langage à typage statique. Compensé par
  `mypy --strict` bloquant en CI.
- Images de conteneur plus volumineuses, démarrage plus lent.

**Réexamen.** Si l'API devient le goulot d'étranglement mesuré, un service Go pour
les routes de lecture les plus chaudes est envisageable — mais ce serait un
sous-ensemble, pas une migration.

---

<a id="adr-004"></a>
## ADR-004 — PostgreSQL + pgvector, pas de base vectorielle dédiée

**Statut** 🔄 À réexaminer · Phase 0

**Contexte.** La recherche sémantique est une fonctionnalité centrale. L'option
« naturelle » est une base vectorielle spécialisée. Mais deux constats pèsent :
la moitié de la valeur de la recherche vient de la voie **lexicale** (noms propres,
acronymes, montants — voir `AI.md` §6.4), et toute requête est **filtrée par
locataire et souvent par date**.

**Décision.** PostgreSQL 17 avec `pgvector` (index HNSW) comme unique magasin :
données métier, recherche plein texte et vecteurs dans la même base, donc dans la
même requête et la même transaction.

**Alternative écartée.** Pinecone, Qdrant ou Weaviate en complément de PostgreSQL.
Meilleures performances vectorielles pures, mais : (1) deux magasins à maintenir
cohérents, avec la classe de bugs qui va avec — un vecteur orphelin après suppression
est une fuite de données ; (2) la fusion lexical/vectoriel devient une opération
applicative au lieu d'une requête SQL ; (3) le filtrage par locataire quitte le
périmètre de la RLS, ce qui affaiblit la garantie d'isolation (ADR-005) ; (4) un
service et un contrat de plus.

**Coût accepté.**
- Performance vectorielle inférieure à un moteur dédié. Sans conséquence jusqu'à
  environ 10 millions de vecteurs ; au-delà, à mesurer.
- Le rappel HNSW se dégrade sous filtre très sélectif — problème connu de `pgvector`.
  Atténué par une bascule vers un parcours exact selon la cardinalité estimée
  (`Database.md` §7.3), ce qui ajoute de la complexité au service de recherche.
- Les vecteurs représentent ~41 % de la taille de la base, ce qui pèse sur les
  sauvegardes et les restaurations.
- Le réglage de l'index HNSW (`m`, `ef_construction`, `ef_search`) demande une
  compétence qu'on n'a pas encore.

**Réexamen.** Déclencheurs : plus de 20 millions de chunks, ou latence de recherche
p95 supérieure à 300 ms, ou rappel mesuré sous 85 %. Le schéma prévoit déjà le
partitionnement de `chunk` pour retarder l'échéance.

---

<a id="adr-005"></a>
## ADR-005 — Isolation multi-locataire par Row Level Security

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le produit stocke ce qu'une personne dit quand elle pense à voix haute :
la donnée la plus intime qu'un outil professionnel puisse détenir. Une fuite entre
comptes ne serait pas un incident, ce serait la fin du produit. Le filtrage
applicatif classique — une clause `WHERE account_id = …` dans chaque requête — repose
entièrement sur la rigueur du développeur, sur des milliers de requêtes, pendant des
années.

**Décision.** Base unique, colonne `account_id` sur chaque table portant des données
utilisateur, Row Level Security active et **forcée** sur toutes ces tables. Le
contexte de locataire est posé par `SET LOCAL app.account_id` au début de chaque
transaction. Un test d'intégration parcourt chaque table et tente une lecture
inter-locataires : toute ligne retournée fait échouer la CI.

**Alternative écartée.**
- *Filtrage applicatif seul.* Une seule requête sans filtre suffit à fuiter. Le
  risque croît avec la taille du code et la rotation de l'équipe.
- *Une base ou un schéma par locataire.* Isolation maximale, mais migrations
  ingérables au-delà de quelques centaines de comptes, et coût de connexion
  prohibitif.

**Coût accepté.**
- Surcharge de requête de l'ordre de 5 à 15 % selon les plans d'exécution.
- Toute connexion doit poser son contexte : une connexion mal configurée ne voit
  rien, ce qui produit des bugs déroutants (« la requête ne retourne rien alors que
  les données existent »).
- Le regroupement de connexions doit utiliser `SET LOCAL` et non `SET`, sous peine
  de fuite de contexte entre requêtes — piège subtil, à couvrir par un test.
- Les traitements de maintenance (purges RGPD) exigent un rôle qui contourne la RLS,
  donc une surface privilégiée à protéger.
- Le débogage en production est plus délicat : sans contexte, on ne voit rien.

---

<a id="adr-006"></a>
## ADR-006 — arq sur Redis plutôt que Celery

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le pipeline de traitement est asynchrone par nature : transcription,
extraction, indexation. Il faut une file de tâches avec priorités, reprises et
planification. Le choix de référence en Python est Celery.

**Décision.** `arq` sur Redis, qui est déjà présent pour le cache et les quotas.

**Alternative écartée.**
- *Celery.* Beaucoup plus riche : routage complexe, chaînes, groupes, écosystème
  d'outils. Mais son modèle est fondamentalement synchrone, ce qui cadre mal avec un
  pipeline où presque tout est de l'attente réseau. Sa configuration est vaste et ses
  modes d'échec sont subtils.
- *RabbitMQ ou SQS.* Garanties de livraison supérieures, mais un composant
  d'infrastructure de plus, et des garanties dont on n'a pas besoin : nos tâches sont
  idempotentes et rejouables depuis la base.

**Coût accepté.**
- Communauté et écosystème nettement plus réduits ; en cas de problème pointu, il
  faudra lire le code source.
- Redis n'offre pas de persistance forte : une perte Redis perd la file. Atténué par
  un balayage périodique de la base qui remet en file les captures bloquées — la
  vérité est en base, pas dans la file.
- Pas de routage sophistiqué. On s'en tient à quatre files et des priorités simples,
  ce qui est de toute façon souhaitable.
- Redis devient un point de défaillance partagé (cache, quotas, files).

---

<a id="adr-007"></a>
## ADR-007 — STT auto-hébergé avec repli SaaS

**Statut** 🔄 À réexaminer · Phase 0

**Contexte.** La transcription est le poste de coût le plus prévisible et le plus
volumineux : chaque seconde d'audio doit être traitée. À 6 000 captures par jour, le
choix entre auto-hébergement et API a un effet direct sur la viabilité économique.
S'y ajoute une considération de confidentialité : l'audio est la donnée la plus
sensible du produit.

**Décision.** `faster-whisper large-v3` auto-hébergé sur un nœud GPU, avec un repli
SaaS déclenché par disjoncteur. Une abstraction unique (`TranscriberPort`) masque les
deux implémentations.

**Alternative écartée.**
- *100 % SaaS.* Aucune infrastructure GPU à opérer, mise à l'échelle immédiate.
  Mais un coût marginal environ huit fois supérieur, l'audio de tous les
  utilisateurs envoyé à un tiers, et une dépendance de disponibilité totale sur le
  chemin critique de valeur.
- *100 % auto-hébergé sans repli.* Coût minimal, mais un incident GPU arrête le
  produit. Inacceptable pour une fonction aussi centrale.

**Coût accepté.**
- Opérer un nœud GPU : pilotes, mémoire, mise à l'échelle, coûts fixes même à faible
  charge. C'est une compétence que l'équipe doit acquérir.
- Le repli élargit la surface de données : en incident, l'audio part chez un tiers.
  Doit figurer explicitement dans la politique de confidentialité.
- Deux chemins à évaluer, à surveiller et à maintenir. Le repli, peu emprunté, est
  celui qui cassera silencieusement — il faut le tester régulièrement.
- Latence de démarrage à froid lors d'une montée en charge.

**Réexamen.** Si l'usage du repli dépasse durablement 5 % du volume, l'hypothèse de
capacité est fausse. Si le coût du GPU dépasse celui du SaaS équivalent, le volume
ne justifie pas l'auto-hébergement.

---

<a id="adr-008"></a>
## ADR-008 — Claude pour l'extraction structurée

**Statut** 🔄 À réexaminer · Phase 0

**Contexte.** L'extraction transforme une transcription en objets typés. C'est
l'étape qui fait la différence entre « une app de notes vocales » et MindFlow. Deux
qualités comptent plus que tout : le respect strict du schéma de sortie, et
l'absence de fabrication — un modèle qui invente une échéance détruit la confiance.

**Décision.** `claude-opus-5` pour l'extraction standard et la synthèse de réunion,
`claude-haiku-4-5` pour le préfiltrage (ADR-019), avec sortie contrainte par schéma
JSON. L'accès passe par un adaptateur (`LlmPort`) et le schéma de sortie est
indépendant du fournisseur.

**Alternative écartée.**
- *Modèle ouvert auto-hébergé.* Coût marginal quasi nul, données qui ne sortent pas.
  Mais le respect strict d'un schéma complexe et la calibration de la confiance sont
  nettement moins fiables, et fiabiliser cela demanderait un travail d'ingénierie
  que l'équipe n'a pas le temps de mener avant d'avoir validé le produit.
- *Un modèle unique pour tous les usages.* Simple, mais fait payer le prix fort pour
  classer une phrase de huit mots.

**Coût accepté.**
- Dépendance à un fournisseur unique, sur le chemin critique de valeur : sa
  disponibilité, ses prix et sa politique de contenu deviennent nos contraintes.
- Coût par appel qui domine l'économie unitaire — c'est l'écart identifié dans
  `AI.md` §7.3.
- Les transcriptions partent chez un tiers. Contrat sans rétention ni entraînement,
  transfert hors UE documenté (ADR-024, `Architecture.md` §11.8).
- Un classifieur de sécurité peut refuser un contenu légitime. Traité comme un état
  dégradé, jamais comme une perte (`AI.md` §9.2).

**Réexamen.** Trois déclencheurs : le coût dépasse durablement le budget après
optimisation ; un modèle ouvert atteint un respect de schéma équivalent sur notre
jeu d'évaluation ; le taux de refus de contenu dépasse 0,5 %.

---

<a id="adr-009"></a>
## ADR-009 — Capture offline-first et idempotence par identifiant client

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le principe P2 du PRD — « la capture ne doit jamais échouer » — est la
promesse la plus forte du produit. Or les captures ont lieu précisément là où le
réseau est mauvais : métro, parking, ascenseur, campagne. Un produit qui perd une
idée parce qu'il n'y avait pas de 4G est un produit mort.

**Décision.**
1. L'audio est écrit sur le disque local **avant** tout accusé de réception à
   l'utilisateur.
2. L'écriture du fichier et l'insertion dans la file locale forment une unité
   atomique.
3. Le client génère un `client_capture_id` (UUIDv7) avant l'enregistrement.
4. Le serveur traite ce `client_capture_id` comme clé d'idempotence : rejouer un
   envoi retourne la capture existante, sans doublon.
5. La file locale persiste et reprend au redémarrage, avec un backoff exponentiel.

**Alternative écartée.** Upload synchrone avec message d'erreur si le réseau est
absent. Beaucoup plus simple, mais viole le principe fondateur. C'est exactement ce
que font les concurrents, et c'est pour cela que les gens s'envoient des messages sur
WhatsApp — parce que WhatsApp, lui, met en file.

**Coût accepté.**
- Un moteur de synchronisation avec reprise, backoff, résolution de conflits et
  gestion des marqueurs de suppression : la partie la plus complexe du client.
- L'espace disque local devient une ressource à gérer, avec une purge et une
  information à l'utilisateur.
- L'état d'une capture est distribué entre le client et le serveur, ce qui rend le
  débogage plus difficile.
- La mémorisation des réponses idempotentes côté serveur ajoute du stockage et une
  logique d'expiration.

---

<a id="adr-010"></a>
## ADR-010 — Table outbox plutôt qu'un bus de messages

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Plusieurs écritures métier doivent déclencher des effets : une entrée
créée déclenche une indexation, une tâche datée programme un rappel, une capture
terminée envoie une notification. Écrire en base puis publier un message expose au
problème classique : la base réussit, la publication échoue, l'effet est perdu.

**Décision.** Motif *transactional outbox* : l'événement est écrit dans une table
`outbox` **dans la même transaction** que l'écriture métier. Un dispatcher lit les
événements en attente et les publie dans les files.

**Alternative écartée.** Kafka ou NATS. Apportent le rejeu longue durée, la
distribution et l'ordre par partition. Mais c'est un composant d'infrastructure
majeur à opérer, pour un besoin que la table couvre entièrement à ce stade — et le
problème de cohérence dual-write resterait entier sans outbox de toute façon.

**Coût accepté.**
- Latence de propagation de l'ordre de la seconde (intervalle du dispatcher), au
  lieu du milliseconde.
- La table `outbox` grossit et demande une purge périodique.
- Le dispatcher est un point de défaillance ; il doit être surveillé et disposer
  d'un verrou distribué pour éviter les traitements en double.
- Pas de rejeu historique au-delà de la rétention de la table.
- Livraison au moins une fois : tous les consommateurs doivent être idempotents.

---

<a id="adr-011"></a>
## ADR-011 — Le brut est immuable, les dérivés sont jetables

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Les modèles changent, les prompts s'améliorent, les schémas évoluent.
Si les données dérivées écrasaient les données brutes, chaque amélioration du modèle
serait inapplicable au passé — et chaque bug de traitement serait définitif.

**Décision.** `capture` et `transcript` sont immuables après création. Une nouvelle
transcription crée une révision, elle n'écrase pas. Toute donnée dérivée — entrées,
chunks, embeddings, liens — peut être régénérée à partir du brut. Le pipeline est
rejouable de bout en bout.

**Alternative écartée.** Mise à jour sur place, plus économe en stockage. Mais elle
rend le retraitement impossible et fait de chaque bug de traitement une perte
définitive.

**Coût accepté.**
- Stockage supérieur : plusieurs révisions de transcription coexistent.
- Complexité de lecture : il faut toujours filtrer sur `is_current`.
- Un retraitement massif est une opération coûteuse à planifier, pas un simple
  script.
- **Exception nécessaire** : l'édition manuelle d'une entrée doit survivre à tout
  retraitement (ADR-027). L'immuabilité s'applique au brut, pas aux corrections
  humaines.

---

<a id="adr-012"></a>
## ADR-012 — Pas de chiffrement de bout en bout au MVP

**Statut** ⚠️ Provisoire · Phase 0

**Contexte.** Le produit stocke des pensées personnelles et des conversations
professionnelles. Le chiffrement de bout en bout serait l'argument de confiance
définitif, en particulier pour le persona Karim, méfiant par construction. Mais il
est **structurellement incompatible** avec le cœur du produit : on ne peut pas
transcrire, extraire, ni indexer sémantiquement ce que le serveur ne peut pas lire.

**Décision.** Pas de chiffrement de bout en bout au MVP. À la place, un ensemble de
garanties vérifiables :
- chiffrement au repos avec une clé par locataire, gérée par KMS ;
- chiffrement en transit TLS 1.3 partout ;
- isolation par RLS, testée automatiquement (ADR-005) ;
- aucun entraînement sur les données utilisateur, contractuellement établi ;
- suppression effective et prouvée par certificat ;
- transparence complète sur les sous-traitants et les traitements.

**Alternative écartée.**
- *E2E complet.* Impliquerait de faire tourner la transcription et l'extraction sur
  l'appareil. Techniquement envisageable pour la transcription à l'horizon de
  quelques années, irréaliste aujourd'hui pour l'extraction, et incompatible avec la
  recherche sémantique côté serveur.
- *E2E partiel (audio chiffré, texte en clair).* Sécurité en trompe-l'œil : le texte
  contient toute l'information sensible. Pire qu'une position honnête.

**Coût accepté.**
- Perte d'un argument de vente fort auprès des utilisateurs les plus soucieux de leur
  vie privée, et impossibilité d'adresser certains marchés réglementés.
- MindFlow peut techniquement lire les données de ses utilisateurs. Cela doit être
  **dit explicitement**, pas dissimulé derrière un vocabulaire flou. Une communication
  ambiguë sur ce point serait plus dommageable que l'absence de la fonctionnalité.
- Surface de risque en cas de compromission de l'infrastructure.

**Réexamen.** v3.0, avec le traitement local sur appareil. Un mode « journal
personnel » chiffré de bout en bout, sans traitement IA, est envisageable plus tôt
comme fonctionnalité distincte — à condition que ses limites soient claires.

---

<a id="adr-013"></a>
## ADR-013 — Transcription en flux pendant les réunions

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Une réunion de 45 minutes transcrite après coup demande environ 4 à 6
minutes de traitement. L'utilisateur qui sort de réunion et veut son compte-rendu
attend. Or c'est précisément le moment où il en a besoin — avant la réunion suivante.

**Décision.** L'audio est envoyé par blocs de 60 secondes pendant l'enregistrement et
transcrit au fil de l'eau en file basse priorité. À la fin, seule la synthèse reste à
faire, ce qui prend de 20 à 60 secondes.

**Alternative écartée.** Traitement après coup, en un seul bloc. Beaucoup plus
simple, sans gestion de blocs, de frontières ni de recollement. Mais le délai perçu
passe de moins d'une minute à cinq minutes, ce qui change la nature de l'usage.

**Coût accepté.**
- Complexité d'implémentation : découpage, envoi par blocs, recollement, correction
  des frontières où un mot peut être coupé.
- Consommation de batterie et de données pendant l'enregistrement — pénalisant en
  déplacement.
- Un bloc perdu doit être détecté et redemandé.
- Coût STT légèrement supérieur : les chevauchements sont transcrits deux fois.
- Si l'enregistrement est annulé, le travail déjà fait est perdu.

---

<a id="adr-014"></a>
## ADR-014 — Riverpod pour la gestion d'état Flutter

**Statut** ✅ Acceptée · Phase 0

**Contexte.** L'état du client est plus subtil qu'il n'y paraît : la base locale est
la source de vérité, la synchronisation modifie l'état en arrière-plan, les mises à
jour optimistes doivent pouvoir être annulées, et le SSE pousse des changements.

**Décision.** Riverpod, avec génération de code pour les providers.

**Alternative écartée.**
- *BLoC.* Très structuré et éprouvé, mais verbeux, et son modèle événement/état
  s'accorde mal avec un état dérivé d'un flux de base de données.
- *Provider seul.* Trop peu structurant pour un état dérivé complexe.
- *setState.* Hors sujet à cette échelle.

**Coût accepté.**
- Courbe d'apprentissage réelle : les providers, leur portée et leur cycle de vie
  demandent un temps d'appropriation.
- La génération de code ajoute une étape de build et du bruit dans les diffs.
- Un mauvais usage produit des reconstructions excessives, difficiles à diagnostiquer.
- Attache le projet à un écosystème spécifique.

---

<a id="adr-015"></a>
## ADR-015 — Drift/SQLite comme source de vérité côté client

**Statut** ✅ Acceptée · Phase 0

**Contexte.** L'application doit fonctionner hors ligne (ADR-009), afficher
instantanément et se synchroniser en arrière-plan. L'interface ne doit jamais
attendre le réseau.

**Décision.** Drift au-dessus de SQLite. La base locale est la source de vérité de
l'affichage ; le serveur est un pair de synchronisation. L'interface observe des flux
issus de la base, jamais des réponses HTTP.

**Alternative écartée.**
- *Hive ou Isar.* Plus rapides pour du clé-valeur, mais sans les requêtes
  relationnelles dont on a besoin (filtres par type, par projet, par date, tris).
- *Cache HTTP seul.* Ne permet ni l'édition hors ligne ni la file de captures.

**Coût accepté.**
- Un schéma de plus à maintenir et à faire évoluer, avec ses migrations propres.
- Le schéma local et le schéma serveur divergent nécessairement — le local est un
  sous-ensemble dénormalisé. Deux modèles à garder cohérents.
- Poids et temps de démarrage supérieurs à un magasin clé-valeur.
- Les migrations locales échouent sur les appareils des utilisateurs, où l'on ne peut
  pas intervenir : elles doivent être défensives et toujours réversibles vers une
  resynchronisation complète.

---

<a id="adr-016"></a>
## ADR-016 — Code natif pour les widgets et wearables

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le principe P1 du PRD impose un tap depuis l'écran verrouillé. Les
widgets d'écran verrouillé iOS (WidgetKit), les tuiles Android et les applications de
montre n'ont pas d'équivalent Flutter viable.

**Décision.** Ces surfaces sont écrites en natif — SwiftUI et Kotlin/Compose — et
écrivent l'audio dans un conteneur partagé avec l'application Flutter (App Group sur
iOS, stockage partagé sur Android). La file de synchronisation reste unique, gérée
côté Flutter.

**Alternative écartée.** Renoncer aux widgets au MVP. Économise du travail, mais
sacrifie le principe le plus différenciant du produit. La capture depuis l'écran
verrouillé n'est pas un confort, c'est la fonctionnalité.

**Coût accepté.**
- Deux implémentations natives à écrire, tester et maintenir, plus une troisième et
  une quatrième pour les montres.
- Le partage de données entre extension et application est source de bugs subtils,
  spécifiques à chaque plateforme.
- Contraintes de mémoire strictes dans les extensions iOS.
- Les tests automatisés de ces surfaces sont difficiles ; une part de vérification
  restera manuelle.

---

<a id="adr-017"></a>
## ADR-017 — SQLAlchemy 2 + Alembic + Pydantic v2

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Il faut un accès aux données typé et asynchrone, des migrations
réversibles, et une validation d'API cohérente avec la génération d'OpenAPI.

**Décision.** SQLAlchemy 2 en mode asynchrone pour la persistance, Alembic pour les
migrations, Pydantic v2 pour la validation et la sérialisation. Les modèles
SQLAlchemy et les schémas Pydantic restent **distincts** : les premiers décrivent la
base, les seconds le contrat d'API.

**Alternative écartée.**
- *SQLModel.* Unifie les deux, ce qui est séduisant, mais couple le contrat d'API au
  schéma de base : tout changement de colonne devient un changement d'API.
- *SQL brut.* Contrôle total, mais mapping manuel et perte de typage.

**Coût accepté.**
- Duplication apparente entre modèles et schémas, et code de conversion entre les
  deux. C'est le prix du découplage, et il est assumé.
- SQLAlchemy 2 asynchrone a des pièges spécifiques : chargement paresseux interdit,
  gestion explicite de la session.
- Verbosité générale.

---

<a id="adr-018"></a>
## ADR-018 — Stockage objet pour l'audio, jamais la base

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Un utilisateur produit environ 216 Mo d'audio par an. À 5 000
utilisateurs, cela représente 1,1 To — cent fois le volume de la base relationnelle.

**Décision.** L'audio va dans un stockage objet compatible S3, chiffré, avec des
règles de cycle de vie. La base ne stocke que la clé d'objet. L'upload et le
téléchargement passent par des URL présignées de courte durée : l'audio ne transite
jamais par l'API.

**Alternative écartée.**
- *Colonnes `bytea`.* Cohérence transactionnelle, mais gonfle les sauvegardes d'un
  facteur cent, sature le WAL et coûte environ vingt fois plus cher.
- *Disque local sur les nœuds.* Non durable, non partagé, incompatible avec la mise
  à l'échelle.

**Coût accepté.**
- Cohérence non transactionnelle : la base peut référencer un objet qui n'existe pas
  encore, ou l'inverse. Traité par des états explicites et un balayage de
  réconciliation.
- La suppression RGPD doit orchestrer deux systèmes, avec vérification explicite que
  le préfixe est vide avant d'émettre le certificat.
- Les URL présignées sont un vecteur de fuite si elles sont partagées : durée réduite
  à 5 minutes et liaison à l'utilisateur.
- Latence réseau supplémentaire au téléchargement.

---

<a id="adr-019"></a>
## ADR-019 — Aiguillage par complexité avant l'extraction

**Statut** ⚠️ Provisoire · Phase 0

**Contexte.** Faire traiter « rappeler Paul demain » par le modèle le plus capable
est un gaspillage. L'extraction représente 87 % du coût unitaire (`Architecture.md`
§15.2) : c'est le seul levier qui compte vraiment.

**Décision.** Un aiguillage déterministe — comptage de mots, détection de motifs, sans
appel de modèle — dirige chaque capture vers l'une de trois voies : triviale
(règles + `claude-haiku-4-5`), standard (`claude-opus-5`), longue (résumé par blocs
puis synthèse).

**Alternative écartée.**
- *Un seul modèle pour tout.* Simple, prévisible en qualité, mais 2,5 fois plus cher.
- *Aiguillage par modèle.* Un appel pour décider quel appel faire : le coût de la
  décision approche celui du traitement.

**Coût accepté.**
- Trois chemins à évaluer, à surveiller et à maintenir. Chacun peut régresser
  indépendamment.
- Un mauvais aiguillage produit une extraction dégradée sur une capture qui méritait
  mieux — visible par l'utilisateur.
- Le critère d'aiguillage est un heuristique qui devra être ajusté avec les données.
- **La répartition estimée (35 / 55 / 10) n'est pas mesurée.** Si la part triviale
  est nettement plus faible, l'économie du produit change. C'est la principale
  incertitude quantitative de la phase 0.

**Réexamen.** Sprint 3, sur la base de la distribution réelle mesurée. Voir la
matrice d'arbitrage de `AI.md` §7.3.

---

<a id="adr-020"></a>
## ADR-020 — Résolution temporelle déterministe, pas par le LLM

**Statut** ✅ Acceptée · Phase 0

**Contexte.** « Jeudi » doit devenir une date exacte. Cela dépend du jour de la
capture, du fuseau de l'utilisateur, du changement d'heure et de conventions
(« jeudi » signifie-t-il le prochain jeudi, ou celui de cette semaine s'il n'est pas
passé ?). Une échéance fausse est l'erreur qui détruit la confiance le plus vite —
plus vite qu'un mauvais titre ou qu'un type erroné.

**Décision.** Le modèle **repère** l'expression temporelle et la retourne brute
(`temporal_expression`). Un module déterministe la **résout**, avec le fuseau et
l'horodatage de capture. En cas d'ambiguïté irréductible, aucune date n'est produite
et l'expression est conservée dans le corps de l'entrée.

**Alternative écartée.** Demander directement une date ISO au modèle. Une ligne de
prompt en moins, mais : les modèles se trompent sur l'arithmétique de calendrier,
ignorent les changements d'heure, et — surtout — produisent une date **plausible et
fausse** sans aucun signal d'incertitude. Une erreur silencieuse est le pire mode de
défaillance possible pour cette fonction.

**Coût accepté.**
- Un module de résolution à écrire, tester et maintenir, avec une couverture
  linguistique à construire (français et anglais au MVP).
- Chaque nouvelle langue demande un travail explicite ; le LLM aurait couvert
  n'importe quelle langue immédiatement.
- Les expressions inhabituelles ne sont pas résolues alors que le modèle aurait pu
  s'en sortir. Compromis assumé : ne rien affirmer plutôt que se tromper.
- Nécessite un jeu de tests couvrant les changements d'heure, les années bissextiles
  et les fuseaux non entiers.

---

<a id="adr-021"></a>
## ADR-021 — Embeddings auto-hébergés

**Statut** 🔄 À réexaminer · Phase 0

**Contexte.** Chaque entrée et chaque transcription doit être vectorisée, soit
environ 3 400 embeddings par utilisateur et par an. Le texte est court et le volume
élevé — le profil exact où le coût réseau et par appel d'une API domine.

**Décision.** Un modèle d'embedding multilingue auto-hébergé, 1024 dimensions, sur le
même nœud GPU que le STT (les deux charges sont complémentaires : le STT est
sollicité en pointe, l'indexation peut être lissée).

**Alternative écartée.** API d'embeddings. Aucune infrastructure, qualité
généralement supérieure. Mais un coût récurrent sur un volume élevé, une latence
réseau sur chaque indexation, et une dépendance de plus.

**Coût accepté.**
- Un service de plus à opérer, versionner et surveiller.
- Qualité probablement inférieure à un modèle propriétaire de pointe. À mesurer sur
  le jeu d'évaluation RAG — si le rappel passe sous 85 %, la décision est mauvaise.
- Un changement de modèle impose une réindexation complète du corpus. Le schéma le
  prévoit (`embedding_version`), mais l'opération reste coûteuse.
- La dimension 1024 fixe la taille de la colonne : en changer est une migration.

**Réexamen.** Si le rappel mesuré passe sous 85 %, ou si le coût d'exploitation du
GPU dépasse celui d'une API équivalente.

---

<a id="adr-022"></a>
## ADR-022 — Kubernetes managé, Terraform, Helm

**Statut** ✅ Acceptée · Phase 0

**Contexte.** L'infrastructure comporte des composants hétérogènes : API sans état,
workers longue durée, service GPU, planificateur. Il faut de l'autoscaling piloté par
la profondeur des files, et une portabilité entre fournisseurs pour ne pas dépendre
d'un seul acteur sur un produit hébergé en Europe.

**Décision.** Kubernetes managé chez un fournisseur européen, décrit en Terraform,
déployé par Helm.

**Alternative écartée.**
- *PaaS.* Beaucoup plus simple, mais généralement sans support GPU et sans contrôle
  fin de l'autoscaling par file.
- *Serverless.* Inadapté : les workers tournent longtemps, le GPU exige de la
  persistance, et le démarrage à froid est incompatible avec la latence de capture.
- *Machines virtuelles et scripts.* Moins de complexité initiale, mais mise à
  l'échelle manuelle et dérive de configuration garantie.

**Coût accepté.**
- Complexité opérationnelle notable pour une petite équipe. C'est le coût le plus
  discutable de tout le document : Kubernetes est un multiplicateur de complexité.
- Compétence à acquérir et à maintenir.
- Coût fixe du plan de contrôle, non négligeable à faible volume.
- Le risque de sur-ingénierie est réel — il est accepté parce que le nœud GPU et
  l'autoscaling par file rendent les alternatives plus simples inapplicables.

---

<a id="adr-023"></a>
## ADR-023 — GitHub Actions pour la CI/CD

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le pipeline doit exécuter du lint, des tests avec une base réelle, des
analyses de sécurité, des builds mobiles (dont iOS, qui exige macOS) et des
évaluations IA.

**Décision.** GitHub Actions, là où vit le code, avec des runners macOS pour iOS et
des runners GPU pour les évaluations.

**Alternative écartée.**
- *GitLab CI.* Excellent, mais impliquerait de déplacer le dépôt.
- *Jenkins.* Contrôle total, mais un serveur de plus à opérer.
- *CircleCI, Buildkite.* Comparables, sans avantage décisif.

**Coût accepté.**
- Verrouillage modéré sur GitHub : la syntaxe des workflows n'est pas portable.
- Coût des runners macOS et GPU, significatif.
- Les temps de file d'attente ne sont pas maîtrisés.
- Les secrets vivent chez GitHub, ce qui étend la surface de confiance.

---

<a id="adr-024"></a>
## ADR-024 — Hébergement dans l'Union européenne par défaut

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Les personas sont européens. La donnée traitée est de la voix, donc une
donnée personnelle particulièrement sensible. La localisation est à la fois une
exigence réglementaire et un argument commercial face aux acteurs américains.

**Décision.** Toute l'infrastructure — base, stockage objet, workers, STT — est
hébergée dans l'Union européenne. Une exception documentée et assumée : l'API LLM,
hébergée aux États-Unis, encadrée par des clauses contractuelles types et une analyse
d'impact.

**Alternative écartée.**
- *Hébergement américain.* Moins cher, meilleure disponibilité de GPU, latence
  moindre pour les modèles. Mais un handicap commercial en Europe et un risque
  réglementaire.
- *Multi-région dès le départ.* Complexité de réplication et de conformité
  disproportionnée avant d'avoir des clients hors UE.

**Coût accepté.**
- Latence plus élevée pour les utilisateurs hors Europe.
- Capacité GPU européenne moins abondante et plus chère.
- **La transcription reste en Europe, mais le texte part aux États-Unis.** C'est une
  incohérence apparente de la promesse « données en Europe » : elle doit être
  expliquée honnêtement, pas dissimulée. Une formulation vague sur ce point serait
  un manquement.

**Réexamen.** Si un modèle d'extraction de qualité équivalente devient disponible
avec un hébergement européen, la dernière dépendance hors UE disparaît.

---

<a id="adr-025"></a>
## ADR-025 — Un seul appel LLM synchrone : la réponse RAG

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le principe A2 de l'API interdit les appels coûteux sur le chemin
requête/réponse : ils rendent la latence imprévisible et exposent l'API aux
défaillances amont. Mais la recherche en mode `answer` est intrinsèquement
interactive — l'utilisateur pose une question et attend une réponse.

**Décision.** `POST /search` en mode `answer` est la **seule** exception. Elle est
encadrée : périmètre de jeton distinct (`search:answer`), limitation de débit propre
(10/min), délai d'attente strict de 12 secondes, diffusion en flux, et dégradation
automatique vers les résultats bruts en cas de dépassement.

**Alternative écartée.**
- *Tout en asynchrone.* Cohérent avec le principe, mais transformerait « poser une
  question » en « attendre une notification » — inacceptable pour une interaction
  conversationnelle.
- *Sans exception, donc sans mode `answer`.* Sacrifierait le cas d'usage UC-13 et
  l'essentiel du différenciateur « mémoire interrogeable ».

**Coût accepté.**
- Une route dont la latence dépend d'un tiers, et qui peut donc dégrader les
  indicateurs globaux de l'API si elle n'est pas isolée dans les tableaux de bord.
- Une dépendance amont sur le chemin synchrone : une panne LLM rend ce mode
  indisponible.
- Un vecteur de coût exposé directement à l'utilisateur, donc à protéger par des
  quotas stricts.
- Le principe A2 devient « une exception, documentée », ce qui affaiblit sa force
  normative — d'où l'importance de ne pas en ajouter une seconde sans un ADR.

---

<a id="adr-026"></a>
## ADR-026 — Le quota ne bloque jamais une capture

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le plan gratuit limite le nombre de captures mensuelles. La mise en
œuvre évidente est de refuser la création au-delà du quota. Mais le principe P2 —
« la capture ne doit jamais échouer » — est fondateur, et l'utilisateur qui atteint
son quota est précisément celui qui utilise le produit.

**Décision.** `POST /captures` n'est jamais refusé pour dépassement de quota. La
capture est acceptée, l'audio conservé, la transcription effectuée. Seul
l'enrichissement IA est marqué `degraded` et différé. L'utilisateur voit un bandeau
non bloquant. Un passage à Pro déclenche le traitement des captures en attente.

**Alternative écartée.** Refus au-delà du quota, avec un `402`. Modèle économique
plus lisible et incitation à l'upgrade plus forte. Mais perdre une idée pour une
raison commerciale est exactement ce que le produit promet de ne jamais faire — et
c'est le genre d'expérience qui produit une désinstallation, pas une conversion.

**Coût accepté.**
- Coût de stockage et de transcription non couvert par le revenu sur les
  dépassements. Plafonné par une limite absolue anti-abus, très supérieure au quota
  affiché.
- Incitation à l'upgrade plus faible : l'utilisateur n'est jamais bloqué.
- Un état de plus à gérer dans l'interface (« en attente de traitement »).
- Ouvre un vecteur d'abus : plafond absolu et détection de comportement anormal
  nécessaires.

---

<a id="adr-027"></a>
## ADR-027 — L'édition utilisateur prime toujours sur le retraitement IA

**Statut** ✅ Acceptée · Phase 0

**Contexte.** Le pipeline est rejouable (ADR-011) : un prompt amélioré peut être
appliqué au passé. Mais si l'utilisateur a corrigé le type d'une entrée et que le
retraitement le rétablit, l'effet est dévastateur — le produit paraît ignorer ce
qu'on lui dit.

**Décision.** Toute entrée portant `edited_by_user_at` non nul est **exclue** de tout
retraitement automatique sur les champs édités. La colonne fait autorité, en base
comme dans la synchronisation. La même règle s'applique à la résolution de conflits
côté client.

**Alternative écartée.** Fusion intelligente entre correction humaine et
retraitement. Séduisante, mais impossible à rendre prévisible : l'utilisateur ne peut
pas anticiper ce qui sera conservé, et la confiance repose sur la prévisibilité.

**Coût accepté.**
- Une entrée corrigée reste sur l'ancienne interprétation même quand le modèle
  s'améliore. Le corpus se fragmente en deux populations.
- Le suivi doit être fin : `edited_by_user_at` par entrée est un compromis ; un suivi
  par champ serait plus juste mais notablement plus complexe.
- Un utilisateur qui corrige beaucoup ne bénéficie pas des améliorations — ironie
  assumée, mais l'alternative est pire.

---

<a id="adr-028"></a>
## ADR-028 — Suppression d'une capture sans cascade par défaut

**Statut** ✅ Acceptée · Phase 0

**Contexte.** `entry.capture_id` peut être `ON DELETE CASCADE` ou `SET NULL`. La
question est : que veut l'utilisateur qui supprime un enregistrement audio ?

**Décision.** `ON DELETE SET NULL`. Supprimer une capture supprime l'audio et la
transcription ; les entrées qui en sont issues survivent, orphelines de leur source.
La suppression en cascade existe, mais elle est explicite (`?cascade=true`) et
présentée comme une seconde action distincte dans l'interface.

**Alternative écartée.** `CASCADE` par défaut. Plus cohérent en apparence — la source
disparaît, les dérivés aussi — mais catastrophique en pratique : quelqu'un qui
supprime un enregistrement pour des raisons de confidentialité perdrait les tâches
qu'il en a tirées, sans l'avoir voulu.

**Coût accepté.**
- `entry.capture_id` est nullable, et toute l'interface doit gérer l'affichage d'une
  entrée sans source.
- Le principe M2 (« toute donnée dérivée est traçable jusqu'à sa source ») souffre
  une exception permanente.
- Un utilisateur pourrait s'attendre à une suppression complète et être surpris de
  retrouver des tâches. Traité par un libellé explicite au moment de la suppression.
- Deux chemins de suppression à tester.

---

## Décisions non prises — questions ouvertes

Ces points sont volontairement laissés ouverts et doivent être tranchés avant leur
phase respective.

| # | Question ouverte | À trancher avant | Ce qui manque pour décider |
| --- | --- | --- | --- |
| Q1 | Modèle d'extraction final : `opus` partout ou `sonnet` pour la voie standard | Sprint 3 | La distribution réelle de complexité et l'écart de qualité mesuré |
| Q2 | Seuil exact de `needs_review` | Sprint 4 | La calibration de confiance sur données réelles |
| Q3 | `vector(1024)` ou `halfvec(1024)` | v1.1 | La pression mémoire réelle sur l'index HNSW |
| Q4 | Modèle de collaboration : espaces partagés ou partage par entrée | v2.0 | Des entretiens utilisateurs sur l'usage en équipe |
| Q5 | Mode journal chiffré de bout en bout comme fonctionnalité distincte | v2.0 | La demande réelle, mesurée et non supposée |
| Q6 | Reclassement par cross-encoder dans le RAG | v1.2 | Un jeu d'évaluation RAG suffisamment fourni |
| Q7 | Prix réel du palier Pro | Avant l'ouverture publique | Des tests tarifaires |
| Q8 | Second fournisseur LLM pour la redondance | v1.2 | Le coût réel de l'abstraction et la qualité comparée |

---

## Références

- Architecture générale → `Architecture.md`
- Modèle de données → `Database.md`
- Contrat d'API → `API.md`
- Architecture IA → `AI.md`
- Trajectoire → `Roadmap.md`
