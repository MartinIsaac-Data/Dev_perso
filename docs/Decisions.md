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
| [029](#adr-029) | Supabase Auth remplace l'authentification auto-hébergée | ✅ | 1 |
| [030](#adr-030) | Supabase Storage comme magasin d'objets | ✅ | 1 |
| [031](#adr-031) | OpenAI par défaut, architecture interchangeable | ⚠️ | 1 |
| [032](#adr-032) | Python 3.11 au lieu de 3.13 | ✅ | 1 |
| [033](#adr-033) | Rôle applicatif non-superutilisateur, obligatoire | ✅ | 1 |
| [034](#adr-034) | File d'attente des captures persistée sur l'appareil | ✅ | 1 |
| [035](#adr-035) | Le fuseau IANA de l'appareil accompagne chaque capture | ✅ | 1 |
| [036](#adr-036) | Mode d'authentification locale pour le développement | ✅ | 1 |
| [037](#adr-037) | La recherche plein texte s'appuie sur une colonne générée | ✅ | 2 |
| [038](#adr-038) | Le fournisseur de notification est stocké par appareil | ✅ | 2 |
| [039](#adr-039) | Une notification push est un pointeur, jamais une copie | ✅ | 2 |
| [040](#adr-040) | Windows non empaqueté programme ses notifications localement | ✅ | 2 |
| [041](#adr-041) | Tous les horodatages sont `timestamptz` | ✅ | 2 |
| [042](#adr-042) | Les travaux inter-tenants ont leur propre connexion | ✅ | 2 |
| [043](#adr-043) | Une sous-tâche n'est pas une entrée | ✅ | 2 |
| [044](#adr-044) | L'occurrence suivante se calcule depuis l'échéance | ✅ | 2 |
| [045](#adr-045) | Aucun fournisseur d'IA n'est couplé au projet : le port est le contrat | ✅ | 3 |
| [046](#adr-046) | La largeur du vecteur est une décision de déploiement | ✅ | 3 |
| [047](#adr-047) | Ce que la base sait exactement ne passe jamais par un modèle | ✅ | 3 |
| [048](#adr-048) | Une question n'est pas une requête de recherche | ✅ | 3 |
| [049](#adr-049) | La résolution d'entités est déterministe, l'extraction ne l'est pas | ✅ | 3 |
| [050](#adr-050) | Le découpage est synchrone, l'encodage est asynchrone | ✅ | 3 |
| [051](#adr-051) | La mémoire ne retient que le durable, et l'oubli est définitif | ✅ | 3 |
| [052](#adr-052) | Les résumés reçoivent leurs chiffres comme des faits établis | ✅ | 3 |
| [053](#adr-053) | Les prompts sont des artefacts versionnés, dans un dossier dédié | ✅ | 3 |
| [054](#adr-054) | La visibilité par espace est une politique **restrictive** | ✅ | 4 |
| [055](#adr-055) | Le compte *est* l'organisation | ✅ | 4 |
| [056](#adr-056) | Un conflit de synchronisation est classé, jamais résolu tout seul | ✅ | 4 |
| [057](#adr-057) | Un seul port pour sept connecteurs, dont un qui n'est pas un service | ✅ | 4 |
| [058](#adr-058) | Les jetons sont chiffrés avec un trousseau versionné | ✅ | 4 |
| [059](#adr-059) | Le journal d'audit est partitionné par mois | ✅ | 4 |
| [060](#adr-060) | Les dossiers de plateforme que l'on modifie sont du source | ✅ | 4 |
| [061](#adr-061) | Le stockage local est un port, pas `dart:io` | ✅ | 4 |
| [062](#adr-062) | L'analyse en réunion se déclenche sur un signal, pas sur une horloge | ✅ | 4 |
| [063](#adr-063) | Le CORS est ouvert en développement, fermé par défaut ailleurs | ✅ | 4 |
| [064](#adr-064) | Le `state` OAuth est chiffré, et ne stocke rien | ✅ | 4 |

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

---

# Amendements — Phase 1

Ces ADR amendent des décisions de la phase 0. Ils sont ajoutés plutôt que
substitués : l'ADR d'origine reste lisible, avec son raisonnement, et l'amendement
dit ce qui change et pourquoi.

<a id="adr-029"></a>
## ADR-029 — Supabase Auth remplace l'authentification auto-hébergée

**Statut** ✅ Acceptée · Phase 1 · **Amende** `API.md` §4 (lien magique auto-hébergé)

**Contexte.** La phase 0 spécifiait un lien magique implémenté en interne, avec
rotation de jeton de rafraîchissement et détection de rejeu (`API.md` §4.2). La
stack de la phase 1 impose Supabase Auth.

**Décision.** Supabase Auth devient le fournisseur d'identité. Le backend ne délivre
plus de jetons : il **vérifie** ceux de Supabase (HS256 avec le secret projet, ou
asymétrique via JWKS) et projette chaque `auth.users.id` sur une ligne `app_user`
via la colonne `auth_subject`.

**Alternative écartée.** Conserver l'implémentation maison. Elle reste défendable —
elle évite une dépendance sur le chemin critique de connexion — mais représente
plusieurs semaines de travail sur un problème résolu, et la rotation de jeton avec
détection de rejeu est précisément le genre de code où une erreur subtile est une
faille.

**Coût accepté.**
- Dépendance d'un tiers sur le chemin de connexion : Supabase indisponible = personne
  ne se connecte. Les sessions en cours survivent (le jeton est vérifié localement).
- La révocation immédiate d'une session n'est plus sous notre contrôle direct.
- L'identité vit à deux endroits (Supabase et `app_user`) : la synchronisation est un
  point de défaillance, traité par un approvisionnement paresseux au premier appel.
- **La RLS ne change pas.** Le contexte reste posé par `SET LOCAL app.account_id`
  depuis le backend, et non par `auth.uid()` : le motif Supabase natif supposerait
  que le client parle directement à PostgreSQL, ce que cette architecture ne fait pas.
  ADR-005 est préservé intégralement.

<a id="adr-030"></a>
## ADR-030 — Supabase Storage comme magasin d'objets

**Statut** ✅ Acceptée · Phase 1 · **Précise** ADR-018

**Contexte.** ADR-018 exige un stockage objet compatible S3 avec URL présignées.

**Décision.** Supabase Storage. C'est une implémentation de ce qu'ADR-018 décrivait ;
la décision d'origine n'est pas modifiée, seulement instanciée. Un adaptateur local
sur disque sert au développement et aux tests.

**Coût accepté.** Les URL signées de Supabase ont leur propre format et leur propre
politique d'expiration ; l'adaptateur absorbe la différence. Le chiffrement par clé
de locataire (ADR-005, `Architecture.md` §11.4) n'est pas fourni nativement et est
reporté — **c'est un écart réel par rapport à la phase 0**, consigné dans `TODO.md`.

<a id="adr-031"></a>
## ADR-031 — OpenAI comme fournisseur par défaut, architecture interchangeable

**Statut** ⚠️ Provisoire · Phase 1 · **Amende** ADR-008 et ADR-019

**Contexte.** ADR-008 retenait Claude (`claude-opus-5`) pour l'extraction, sur un
critère de respect strict du schéma. La stack de la phase 1 impose OpenAI, avec la
mention explicite « architecture interchangeable ».

**Décision.** OpenAI (`gpt-4o-mini` par défaut) devient le fournisseur configuré ;
Claude reste implémenté comme adaptateur alternatif. Le choix se fait par
configuration (`MINDFLOW_LLM_BACKEND`), sans redéploiement de code. Le schéma de
sortie (`app/domain/analysis.py`) est indépendant du fournisseur et c'est lui, et non
le prompt, qui constitue le contrat.

**Alternative écartée.** Conserver Claude comme défaut. Le raisonnement d'ADR-008
reste valable, mais il n'a jamais été vérifié par une mesure : la question Q1 de la
phase 0 est toujours ouverte, et aucune donnée ne permet aujourd'hui de trancher.

**Coût accepté.**
- **Le raisonnement d'ADR-008 n'est pas invalidé, il est simplement mis de côté sans
  preuve.** L'affirmation « la qualité d'extraction structurée est décisive » reste
  non mesurée. Le dispositif d'évaluation (`AI.md` §8) est le seul moyen de trancher,
  et il doit comparer les deux adaptateurs sur le même jeu.
- Deux adaptateurs à maintenir et à évaluer.
- Les estimations de coût de `Architecture.md` §15.2 sont caduques : elles étaient
  calculées sur les tarifs Claude. À recalculer.

**Réexamen.** Sprint 3, sur le jeu d'évaluation, exactement comme le prévoyait Q1.

<a id="adr-032"></a>
## ADR-032 — Python 3.11 au lieu de 3.13

**Statut** ✅ Acceptée · Phase 1 · **Amende** ADR-003

**Contexte.** ADR-003 visait Python 3.13 ; l'environnement de développement fournit
3.11.

**Décision.** Cibler `>=3.11`. Aucune fonctionnalité de 3.12 ou 3.13 n'est utilisée.

**Coût accepté.** On se prive de quelques améliorations de performance et de messages
d'erreur. La montée de version sera un changement de `requires-python` et d'image de
base, sans modification de code.

<a id="adr-033"></a>
## ADR-033 — Rôle applicatif non-superutilisateur, obligatoire

**Statut** ✅ Acceptée · Phase 1 · **Complète** ADR-005

**Contexte.** Découvert à l'implémentation : `FORCE ROW LEVEL SECURITY` fait
s'appliquer les politiques au propriétaire de la table, mais **un superutilisateur
contourne toujours la RLS**. Une application connectée en `postgres` rend donc
inertes toutes les politiques de la migration 0002 — la garantie d'isolation serait
purement décorative.

**Décision.** Trois rôles (`mindflow_app`, `mindflow_readonly`,
`mindflow_maintenance`) créés par la migration 0003. L'application se connecte
obligatoirement avec `mindflow_app` : `NOSUPERUSER`, `NOBYPASSRLS`. Un test
(`test_the_app_role_cannot_bypass_rls`) vérifie cette propriété à chaque exécution
de la suite.

**Coût accepté.** Un rôle de plus à provisionner dans chaque environnement, et une
configuration de connexion qui ne peut pas être « simplifiée » en superutilisateur
sans faire échouer les tests — ce qui est l'effet recherché.

<a id="adr-034"></a>
## ADR-034 — File d'attente des captures persistée sur l'appareil

**Statut** ✅ Acceptée · Phase 1 · **Complète** [ADR-009](#adr-009)

**Contexte.** ADR-009 rend le serveur idempotent sur `client_capture_id` : rejouer
une déclaration ne crée pas de doublon. Cela règle la moitié du problème. L'autre
moitié est côté client : si l'application est tuée entre l'arrêt de l'enregistrement
et l'accusé de réception du serveur, l'idempotence serveur ne sert à rien — personne
ne rejouera jamais l'appel. Or le métro, l'ascenseur et l'avion sont exactement les
lieux où l'on capture une pensée.

**Décision.** L'enregistrement est écrit dans un fichier avant tout appel réseau, et
une ligne est ajoutée à `pending_captures.json` **avant** la déclaration. La ligne
n'est retirée qu'après le `complete` accepté par le serveur. Le tableau de bord
rejoue la file à chaque affichage ; l'écran de capture propose un rejeu manuel.

Le rejeu repart de l'étape `declared` même si l'envoi avait réussi : chaque appel
serveur étant idempotent, rejouer trop tôt est sûr, alors que deviner où l'échec
s'est produit ne l'est pas.

**Alternative écartée.** SQLite sur l'appareil. La file contient une poignée de
lignes et subit une écriture par capture ; une base embarquée serait une dépendance
à maintenir pour toujours au profit d'un gain non mesurable.

**Coût accepté.** Un fichier JSON réécrit intégralement à chaque modification —
acceptable à cette volumétrie, à revoir si la file dépasse quelques centaines de
lignes. Une écriture interrompue produit un JSON tronqué : le chargeur le détecte,
supprime le fichier et repart à vide plutôt que de bloquer la file définitivement.
Les fichiers audio, eux, survivent.

**Réexamen.** Si la synchronisation multi-appareils (Roadmap v0.4) impose un état
local plus riche que « ce qui n'est pas encore parti ».

<a id="adr-035"></a>
## ADR-035 — Le fuseau IANA de l'appareil accompagne chaque capture

**Statut** ✅ Acceptée · Phase 1 · **Complète** [ADR-020](#adr-020)

**Contexte.** ADR-020 confie la résolution des dates à un module déterministe côté
serveur. Ce module ne peut résoudre « jeudi » ou « fin de mois » qu'en connaissant le
fuseau dans lequel les mots ont été prononcés. `DateTime.timeZoneName` en Dart ne
renvoie qu'une abréviation (« CEST »), ambiguë entre plusieurs zones et muette sur
les règles de changement d'heure du mois prochain.

**Décision.** Le client résout le nom IANA (`Europe/Paris`) via `flutter_timezone`
et l'envoie dans `capture_timezone` à la déclaration. En cas d'échec de la
plateforme, repli sur `Europe/Paris` — un fuseau erroné décale une échéance de
quelques heures, refuser d'enregistrer coûterait la pensée entière.

**Coût accepté.** Une dépendance de plus, et un repli qui peut être faux pour un
utilisateur hors d'Europe dont la plateforme ne répond pas. Le champ est stocké sur
la capture : une résolution erronée reste auditable et re-calculable.

<a id="adr-036"></a>
## ADR-036 — Mode d'authentification locale pour le développement

**Statut** ✅ Acceptée · Phase 1 · **Complète** [ADR-029](#adr-029)

**Contexte.** Exiger un projet Supabase pour lancer `docker compose up` et le client
en local ajoute un compte tiers au chemin de démarrage. Un projet dont on ne peut pas
faire tourner la pile en cinq minutes est un projet où l'on teste moins.

**Décision.** Un indicateur de compilation `MINDFLOW_LOCAL_AUTH=true` remplace le
dépôt Supabase par une identité locale produisant le même jeton non signé que
`make_local_token` côté serveur. Trois verrous indépendants empêchent que cela
devienne un contournement d'authentification :

1. `Settings` refuse de démarrer en `staging` ou `production` sans méthode de
   vérification de jeton configurée ;
2. `TokenVerifier` ne saute la vérification de signature qu'en `local` et `test` ;
3. l'indicateur est un constant de compilation absent des builds de production.

**Alternative écartée.** Un compte de démonstration partagé sur un vrai projet
Supabase. Cela déplace le secret dans le dépôt au lieu de le supprimer.

**Coût accepté.** Un chemin d'authentification supplémentaire à maintenir, et une
règle à ne jamais assouplir : si un jour le back-end acceptait des jetons non
vérifiés hors `local`/`test`, ce mode deviendrait une porte ouverte. Le test
`test_production_requires_an_auth_verification_method` garde cette propriété.

<a id="adr-037"></a>
## ADR-037 — La recherche plein texte s'appuie sur une colonne générée

**Statut** ✅ Acceptée · Phase 2

**Contexte.** La recherche doit trouver « budget » dans « les budgets annuels »,
sur un corpus qui atteint plusieurs dizaines de milliers d'entrées après deux ans.
`ILIKE '%budget%'` ne lemmatise pas et impose un balayage complet ; un index
maintenu par l'application dérive dès qu'un chemin d'écriture l'oublie.

**Décision.** `entry.search_vector` est une **colonne générée et stockée**,
calculée par PostgreSQL à partir de `title` (poids A) et `body` (poids B), avec
un index GIN. La configuration `french` lemmatise. Les requêtes passent par
`websearch_to_tsquery`, pas `to_tsquery`.

**Alternative écartée.** Un trigger. Il fait le même travail, mais il peut être
désactivé, oublié dans une migration, ou contourné par un `COPY` — une colonne
générée ne le peut pas.

**Coût accepté.** La colonne est recalculée à chaque écriture d'`entry` et occupe
de l'espace. Changer de configuration textuelle imposera une reconstruction de
toute la colonne. `websearch_to_tsquery` est moins expressif que `to_tsquery` —
c'est le prix de la propriété qui compte ici : **il ne peut pas lever
d'exception**. Une barre de recherche ne doit pas pouvoir renvoyer un 500.

<a id="adr-038"></a>
## ADR-038 — Le fournisseur de notification est stocké par appareil

**Statut** ✅ Acceptée · Phase 2

**Contexte.** On pourrait déduire le canal de livraison de la plateforme. C'est
faux dans les deux sens : un téléphone Android et un onglet Chrome passent tous
deux par FCM, et un poste Windows est joignable par WNS (application empaquetée)
ou par une notification programmée localement (exécutable simple).

**Décision.** `device.push_provider` (`fcm`, `wns`, `local`, `none`) est
enregistré à l'inscription de l'appareil, à côté de `platform`. Le répartiteur
groupe par fournisseur et demande l'adaptateur correspondant.

**Coût accepté.** Une colonne de plus, et un client qui doit dire la vérité sur
ce qu'il sait faire. En échange, « ajouter Windows » est un adaptateur, pas une
branche supplémentaire dans le planificateur.

<a id="adr-039"></a>
## ADR-039 — Une notification push est un pointeur, jamais une copie

**Statut** ✅ Acceptée · Phase 2 · **Complète** [ADR-021](#adr-021)

**Contexte.** Une charge push transite par un tiers (Google, Microsoft) et est
stockée en clair sur l'appareil. Elle est aussi figée : une notification envoyée
hier montre le titre d'hier.

**Décision.** La charge contient un titre, une ligne et les identifiants
nécessaires pour ouvrir le bon écran. Jamais la transcription, jamais le corps
d'une entrée. Le contenu est lu depuis l'API à l'ouverture.

**Coût accepté.** L'aperçu sur l'écran verrouillé est moins riche. C'est
exactement l'arbitrage voulu pour un produit qui traite de la parole privée.

<a id="adr-040"></a>
## ADR-040 — Windows non empaqueté programme ses notifications localement

**Statut** ✅ Acceptée · Phase 2

**Contexte.** `flutter build windows` produit un exécutable simple, pas un MSIX.
Un exécutable simple n'a **pas de canal WNS** : il n'existe aucune URI vers
laquelle pousser. Traiter Windows comme Android donnerait un rappel qui n'arrive
jamais, sans erreur nulle part.

**Décision.** Deux chemins, choisis par `push_provider` :

* application empaquetée → `wns`, le serveur pousse ;
* exécutable simple → `local`, le client lit sa propre liste de rappels via
  `GET /v1/reminders` et programme les toasts lui-même.

Le serveur **enregistre quand même** les rappels du canal `local` : ils sont
l'intention, l'appareil n'en est que l'exécutant. Deux vues de « ce qui est
programmé » qui ne peuvent pas être comparées finissent toujours par diverger.

**Coût accepté.** Un rappel local n'arrive que si l'application a été lancée
depuis sa programmation, et le répartiteur ne pousse pas sur ce canal pour ne pas
afficher deux fois la même chose. Le centre de notifications reste, dans tous les
cas, l'enregistrement durable.

<a id="adr-041"></a>
## ADR-041 — Tous les horodatages sont `timestamptz`

**Statut** ✅ Acceptée · Phase 2 · **Corrige** un défaut de la Phase 1

**Contexte.** `created_at`, `updated_at` et quelques autres étaient
`timestamp without time zone`. Découvert en implémentant les statistiques : une
telle colonne se compare comme une heure **locale**, si bien que la filtrer
contre un datetime aware lève une erreur au niveau du pilote et — plus grave — la
grouper par jour dans un rapport donne une réponse décalée du fuseau.

**Décision.** Migration 0005 convertit les 32 colonnes concernées en
`timestamptz`, avec `USING colonne AT TIME ZONE 'UTC'` : les valeurs avaient été
écrites par `now()` sous une session UTC, elles sont donc réinterprétées comme
UTC et non comme l'heure locale du serveur.

**Coût accepté.** Une réécriture de table par colonne convertie. Acceptable
maintenant, coûteux dans un an — raison de plus pour le faire tout de suite.

<a id="adr-042"></a>
## ADR-042 — Les travaux inter-tenants ont leur propre connexion

**Statut** ✅ Acceptée · Phase 2 · **Corrige** un défaut de la Phase 1

**Contexte.** `privileged_session()` prétendait traverser les tenants pour le
balayeur, le répartiteur d'outbox et désormais celui des rappels. Elle utilisait
le moteur applicatif — donc le rôle `mindflow_app`, **`NOBYPASSRLS` par
construction** (ADR-033). Conséquence : ces travaux ne voyaient **aucune ligne**.
Pas d'erreur, pas de log, aucun symptôme jusqu'à ce que quelqu'un remarque que ses
rappels n'arrivent jamais. Aucun test ne le couvrait.

**Décision.** Un second DSN, `MINDFLOW_MAINTENANCE_DATABASE_URL`, pointant sur
`mindflow_maintenance` (`BYPASSRLS`, créé dès la migration 0003 mais jamais
utilisé). `privileged_session()` a son propre moteur, avec un pool réduit. Deux
tests gardent la propriété : l'un vérifie l'attribut du rôle, l'autre lit
réellement la ligne d'un tenant jamais nommé.

**Alternative écartée.** Une politique RLS acceptant un réglage
`app.maintenance = on`. Plus faible : n'importe quel porteur du rôle applicatif
pourrait le poser.

**Coût accepté.** Une variable d'environnement de plus, et un rôle à provisionner.
En développement local, le défaut retombe sur `database_url`, ce qui est correct
puisque l'application y possède le schéma.

<a id="adr-043"></a>
## ADR-043 — Une sous-tâche n'est pas une entrée

**Statut** ✅ Acceptée · Phase 2

**Contexte.** Modéliser une sous-tâche comme une `entry` avec un parent est
tentant : le typage, les tags et la provenance existent déjà.

**Décision.** Table `subtask` distincte, **un seul niveau**. Une sous-tâche a un
titre, une position et un état ; ni type, ni confiance, ni provenance, ni tags.

**Coût accepté.** On ne peut pas taguer une sous-tâche ni la retrouver par
recherche plein texte. En échange, aucune requête de liste du produit n'a besoin
de se souvenir d'exclure les enfants — et une seule qui l'oublie afficherait à
l'utilisateur sa propre liste de courses au milieu de ses décisions. Deux niveaux
d'imbrication, c'est un projet ; les projets existent déjà.

<a id="adr-044"></a>
## ADR-044 — L'occurrence suivante se calcule depuis l'échéance, pas depuis la complétion

**Statut** ✅ Acceptée · Phase 2

**Contexte.** Une tâche « tous les lundis » terminée un mercredi. Deux calculs
possibles : lundi prochain, ou mercredi prochain.

**Décision.** Depuis l'échéance précédente. Et une planification en retard
rattrape le futur **en une seule étape** : rouvrir l'application après trois
semaines d'absence ne doit pas créer trois copies en retard de la même corvée.

**Coût accepté.** Une tâche récurrente jamais terminée n'engendre rien — c'est
voulu : la récurrence décrit un rythme, pas une file d'attente. Le sous-ensemble
de RFC 5545 pris en charge est volontairement petit (`FREQ`, `INTERVAL`, `BYDAY`,
`COUNT`, `UNTIL`) et **rejette** ce qu'il ne comprend pas au lieu de l'approximer.

---

<a id="adr-045"></a>
## ADR-045 — Aucun fournisseur d'IA n'est couplé au projet : le port est le contrat

**Statut** ✅ Acceptée · Phase 3

**Contexte.** La phase 3 devait fonctionner indifféremment avec OpenAI, Claude,
Gemini, Llama et Mistral. La tentation habituelle est d'installer le SDK du
fournisseur retenu et de l'appeler depuis les services, avec l'intention de
« généraliser plus tard ». Cette généralisation n'arrive jamais : au moment où
elle devient nécessaire, le nom du fournisseur est dans quarante fichiers.

**Décision.** Deux ports — `EmbedderPort`, `ChatPort` — et **un seul module dans
tout le dépôt qui connaît le nom d'un fournisseur** : `app/infra/ai/factory.py`.
Aucun SDK vendeur n'est installé ; les adaptateurs parlent HTTP directement, via
`httpx`, déjà présent. Le choix se fait par variable d'environnement.

Cinq fournisseurs pour trois implémentations, parce qu'OpenAI, Mistral et
n'importe quel serveur compatible OpenAI — Ollama, vLLM, llama.cpp, Together —
partagent un format de fil. « Llama » n'est d'ailleurs pas un fournisseur mais
une famille de modèles : son intégration est une URL de base et aucune clé.
Exiger une clé rendrait le seul fournisseur tournant sur votre propre matériel le
plus difficile des cinq à configurer.

**Vérification.** `tests/unit/test_ai_factory.py::test_no_service_imports_a_provider_by_name`
lit les sources et échoue si un module hors de la fabrique nomme un fournisseur.
Une convention non vérifiée est une convention qui tient jusqu'à la première
échéance.

**Coût accepté.** Écrire l'HTTP à la main plutôt qu'utiliser un SDK signifie
suivre soi-même les évolutions de quatre APIs. C'est un coût réel, payé en
échange d'un dépôt où ajouter Mistral a touché la fabrique, un bloc de
configuration et une validation de production — rien d'autre.

---

<a id="adr-046"></a>
## ADR-046 — La largeur du vecteur est une décision de déploiement, pas d'exécution

**Statut** ✅ Acceptée · Phase 3

**Contexte.** `chunk.embedding` est un `vector(N)` de largeur fixe. Les modèles
d'embedding n'ont pas la même dimension : 1536 pour `text-embedding-3-small`,
1024 pour `mistral-embed`, 768 pour `text-embedding-004`. Trois options : une
colonne par largeur, une colonne `vector` sans dimension, ou une largeur fixée
au déploiement.

**Décision.** Largeur fixée au déploiement, lue depuis `embedding_dimensions` par
le modèle SQLAlchemy **et** par la migration 0006, et `embedding_model` enregistré
sur chaque ligne. Les requêtes sémantiques filtrent sur ce modèle.

Le raisonnement décisif n'est pas technique mais mathématique : **deux modèles
produisent des vecteurs dans des espaces différents, et leur distance cosinus n'a
aucune signification**. Changer de fournisseur impose donc de tout réencoder,
quelle que soit la solution retenue. Une colonne sans dimension aurait perdu
l'index HNSW — qui exige une largeur fixe — pour ne rien résoudre.

Le filtre sur `embedding_model` est ce qui rend la migration *dégradante* plutôt
que *corruptrice* : pendant le réencodage, la recherche sémantique ignore les
anciens vecteurs et retrouve moins de choses. Sans lui, elle mélangerait deux
espaces et classerait par rien du tout — un résultat pire qu'un index vide, parce
qu'il a l'air de fonctionner. `reset_embeddings()` est le chemin de migration.

**Coût accepté.** La même migration produit un schéma différent selon la
configuration, ce qui est inhabituel et mérite d'être su. C'est documenté dans
l'en-tête de la migration 0006.

---

<a id="adr-047"></a>
## ADR-047 — Ce que la base sait exactement ne passe jamais par un modèle

**Statut** ✅ Acceptée · Phase 3

**Contexte.** Cinq questions à traiter. Il aurait été plus simple de toutes les
router vers le RAG : un seul chemin, un seul prompt, un seul jeu de tests.

**Décision.** Le routage est **déterministe d'abord** (`app/domain/intent.py`).
Deux des cinq questions n'atteignent jamais un modèle et une ne l'atteint que
pour formuler des nombres calculés en SQL.

| Question | Chemin | Modèle |
| --- | --- | --- |
| « Que dois-je faire aujourd'hui ? » | requête agenda | non |
| « Quelles sont mes tâches en retard ? » | requête agenda | non |
| « Montre les notes concernant X » | récupération → liste | non |
| « Résume mes réunions » | récupération → génération | oui |
| « Quels sujets reviennent souvent ? » | `GROUP BY` → narration | oui, pour la phrase seulement |

Ce n'est pas une optimisation de coût. « Ce qui est dû aujourd'hui » est un fait
que la base connaît exactement ; un modèle interrogé sur la même question ne peut
que l'approximer, plus lentement. Tout router vers la génération rendrait
l'assistant **moins bon** sur les questions les plus fréquentes.

C'est le même principe qu'ADR-020 pour les dates, appliqué au routage : ce qui
peut être calculé exactement ne doit jamais être deviné.

**Vérification.** Le test d'intégration affirme `used_model is False` sur
exactement ces routes. C'est la propriété qu'une refactorisation bien
intentionnée — « simplifions, envoyons tout au LLM » — détruirait en premier.

**Coût accepté.** Une question formulée de façon inattendue tombe dans le RAG
générique. C'est le bon repli : il répond toujours quelque chose de défendable,
et la confiance basse du classifieur dit « aucun raccourci appliqué », pas « je
n'ai pas compris ».

---

<a id="adr-048"></a>
## ADR-048 — Une question n'est pas une requête de recherche

**Statut** ✅ Acceptée · Phase 3

**Contexte.** `websearch_to_tsquery` combine ses termes par **ET**. C'est le bon
comportement pour une barre de recherche, et catastrophique pour une question :
« Pourquoi le fournisseur a-t-il changé ses conditions ? » exigerait que le mot
« pourquoi » figure dans la note. Aucun résultat, jamais.

**Décision.** Deux comportements distincts pour deux usages distincts.
`search_service` — la barre de recherche — garde `websearch_to_tsquery` tel quel.
La récupération de l'assistant construit une requête **disjonctive** à partir des
termes significatifs, en passant toujours par `websearch_to_tsquery` avec le
mot-clé `OR` explicite.

Passer par `websearch_to_tsquery` plutôt que de fabriquer une chaîne `to_tsquery`
conserve la garantie qui l'avait fait choisir (ADR-037) : quoi que tape
l'utilisateur, la fonction ne lève pas. Une barre de recherche ne doit pas
pouvoir renvoyer un 500.

**Complément.** « Résume mes réunions » ne partage aucun mot-clé avec une réunion
et aucun embedding avec un *ensemble* de réunions : c'est une demande de
**parcours d'une tranche filtrée**, pas d'appariement. Quand ni le lexical ni le
sémantique ne trouvent rien, la récupération se rabat sur la récence dans le même
périmètre. C'est ce repli qui rend cette question répondable ; il ne s'applique
qu'en dernier recours, donc une question qui apparie garde son classement.

---

<a id="adr-049"></a>
## ADR-049 — La résolution d'entités est déterministe, l'extraction ne l'est pas

**Statut** ✅ Acceptée · Phase 3

**Contexte.** Le produit détecte sept catégories — personnes, produits,
entreprises, projets, décisions, risques, actions. Deux questions distinctes :
*trouver* « Jean-Marc Ondo » dans une phrase, et *décider* que le « jean marc
ondo » de juillet est la même personne.

**Décision.** La première est confiée au modèle, la seconde au code. La clé de
résolution (`app/domain/knowledge.py`) replie le nom : minuscules, sans accents,
sans ponctuation, sans article de tête. Demander au modèle donnerait une réponse
différente un autre jour, et un graphe de connaissances qui se réorganise tout
seul est pire que pas de graphe.

Les catégories nommables (personne, produit, entreprise, projet) se résolvent sur
le nom seul, donc une personne se retrouve de mois en mois. Les catégories
énonciatives (décision, risque, action) se résolvent sur le texte complet : deux
risques formulés identiquement en mars et en juillet ne sont pas évidemment le
même risque. Fusionner à tort deux décisions en perd une irrémédiablement ;
les séparer à tort n'affiche que deux lignes.

**Une seule table, sept catégories.** Sept tables presque identiques signifieraient
sept requêtes presque identiques pour « quels sujets reviennent souvent ? », et
l'ensemble grandira (`lieu` est évident, `contrat` probable). Le coût est qu'une
colonne propre à une catégorie n'a nulle part où aller : `detail` est un texte
libre, ce qui suffit pour « risque : rupture de stock » et est honnête sur le reste.

**`mention_count` est recalculé, jamais incrémenté.** L'incrément est
l'implémentation évidente et elle est fausse : une seule réindexation double tous
les compteurs du produit, « quels sujets reviennent souvent ? » répond avec des
nombres gonflés, et rien n'a l'air cassé.

---

<a id="adr-050"></a>
## ADR-050 — Le découpage est synchrone et gratuit, l'encodage est asynchrone et payant

**Statut** ✅ Acceptée · Phase 3

**Contexte.** Rendre une note retrouvable demande deux choses : la découper, et
encoder les morceaux. La première est du texte pur ; la seconde est un appel
réseau facturé.

**Décision.** Les deux sont séparées et échouent indépendamment. À l'écriture
d'une entrée, ses `chunk` sont écrits dans la **même transaction**, avec
`embedding` à NULL. Un worker remplit les NULL par lots.

Les fusionner mettrait un appel fournisseur sur le chemin de publication d'une
capture, où une panne devient une perte de données. Séparés, une panne dégrade la
recherche un moment et rien d'autre — le même principe qu'ADR-026 pour les quotas :
le produit se dégrade, il ne bloque pas.

**Il n'existe pas d'état « échec ».** Un lot en échec laisse les lignes à NULL et
le tick suivant les reprend. Un état d'échec exigerait un chemin de remise à zéro
et quelqu'un pour se souvenir qu'il existe.

**La réindexation est incrémentale, par hachage de contenu.** Une entrée corrigée
d'une faute se redécoupe en très majoritairement les mêmes hachages ; seul ce qui
a changé est réencodé. Sans cela, chaque modification réencode toute l'entrée, et
un utilisateur qui range ses notes un dimanche après-midi génère une facture. Le
compteur `unchanged` du résultat est la mesure qui rend cela vérifiable : sur une
modification typique il doit dominer, et un déploiement où il vaut toujours zéro a
un bug de déterminisme du découpage, invisible autrement.

---

<a id="adr-051"></a>
## ADR-051 — La mémoire ne retient que le durable, et l'oubli est définitif

**Statut** ✅ Acceptée · Phase 3

**Contexte.** Sans mémoire, chaque conversation repart de zéro : l'utilisateur
réexplique son rôle, qui est le DAF, qu'il veut des réponses courtes. Avec une
mémoire trop généreuse, le magasin se remplit de « L'utilisateur a demandé un
résumé de ses réunions » — vrai, inutile, et relu à chaque tour à un coût.

**Décision.** Trois règles, appliquées dans le code et non confiées au prompt.

1. **Un seuil de confiance plus haut que partout ailleurs** (0,7). Une entité
   extraite douteuse s'affiche une fois ; une mémoire douteuse façonne toutes les
   réponses futures, sans erreur et sans moyen pour l'utilisateur de deviner la
   cause.
2. **La confiance décroît** — demi-vie de 180 jours, exponentielle et non
   couperet. Un couperet ferait disparaître un fait entre deux tours de la même
   conversation, ce qui se lit comme une amnésie en pleine phrase. La pondération
   porte sur la *dernière confirmation*, pas sur la confiance d'origine : un fait
   devenu faux cesse discrètement d'être utilisé.
3. **Un oubli est définitif.** La ligne survit en pierre tombale et le
   réapprentissage est refusé contre elle. Une suppression sèche laisserait la
   conversation suivante réapprendre exactement ce que l'utilisateur vient de
   rejeter — ce qui lui dit que sa correction n'a pas tenu.

**Tout est inspectable.** `GET /v1/memory` retourne l'intégralité, avec le poids
après décroissance. Un magasin de mémoire que l'utilisateur ne peut pas inspecter
est un magasin qu'il ne peut pas corriger.

---

<a id="adr-052"></a>
## ADR-052 — Les résumés périodiques reçoivent leurs chiffres comme des faits établis

**Statut** ✅ Acceptée · Phase 3

**Contexte.** Un résumé est lu **passivement**, souvent sur une notification, par
quelqu'un qui n'ouvrira pas la source pour vérifier. Une information fausse y est
directement agie.

**Décision.** Les comptages sont calculés en SQL et transmis au modèle comme des
faits, avec interdiction explicite de les recalculer ou de les réordonner. Un
modèle qui dénombre une liste est un moyen documenté de se tromper de deux avec
aplomb.

Trois prompts distincts, un par période, parce que ce qui change entre le
quotidien, l'hebdomadaire et le mensuel n'est pas la longueur mais **ce que le
lecteur cherche** : ce qu'il a oublié de faire, où en sont les sujets, ce qui a
changé. Un seul prompt à période variable produit trois résumés médiocres.

**Les périodes sont des jours dans le fuseau de l'utilisateur**, pas des instants
UTC : « la semaine du 1er juin » doit désigner la même chose à Libreville et à
Paris, et ne pas se décaler quand la personne voyage. D'où `period_start` en
`date`, et un cron **horaire** qui demande à chaque tick quels utilisateurs
viennent d'atteindre leur heure locale.

**Régénérer remplace.** La contrainte d'unicité sur
(compte, utilisateur, période, début) fait qu'un tick qui se déclenche deux fois
produit la même ligne. Deux résumés de la même semaine ne sont pas un historique
plus riche, c'est une contradiction affichée à l'utilisateur.

**Repli sans modèle.** Un cron tourne sans personne pour regarder. En cas de
panne fournisseur, le résumé est rendu **factuel** — les mêmes chiffres, sans la
prose — plutôt que vide. Une période vide produit une phrase explicite, parce que
le silence est ambigu : l'utilisateur ne peut pas distinguer « vous n'avez rien
fait » de « le travail a échoué », et conclura le second.

---

<a id="adr-053"></a>
## ADR-053 — Les prompts sont des artefacts versionnés, dans un dossier dédié

**Statut** ✅ Acceptée · Phase 3

**Contexte.** En phase 1 le prompt d'extraction vivait dans
`app/infra/ai/prompts.py`, à côté de l'adaptateur qui l'envoyait. Cela laissait
entendre que l'adaptateur OpenAI *possédait* ce prompt — faux, et devenu
franchement trompeur dès lors que le fournisseur est interchangeable.

**Décision.** Un dossier `app/prompts/`, hors de `app.infra`, avec un contrat
d'imports vérifié par `import-linter` : un prompt ne peut importer ni fournisseur,
ni framework, ni I/O. C'est du texte neutre ; le même prompt d'extraction part
chez OpenAI, Claude, Gemini, Llama ou Mistral sans modification.

Chaque prompt déclare un nom stable, une version et une **empreinte** — le hachage
du texte réellement envoyé, écrit sur chaque `ai_run`. Quand une réponse est
mauvaise six semaines plus tard, la première question est « qu'avons-nous envoyé
exactement ? », et la seule réponse honnête vient d'une empreinte stockée
pointant vers un texte que personne ne peut modifier discrètement.

**Une propriété de sûreté devient vérifiable.** Le registre permet à un test
d'affirmer que **tout** prompt interpolant du texte utilisateur déclare que ce
texte est une donnée et non une instruction. L'injection par une *capture* n'est
pas hypothétique ici : l'entrée du produit est du texte dicté ou collé, et
quelqu'un lisant un document à voix haute finira par prononcer quelque chose
ayant la forme d'une consigne. Chaque prompt s'en défend individuellement ; seul
un registre permet de vérifier qu'aucun ne l'a oublié.

**Rétrocompatibilité.** `app/infra/ai/prompts.py` subsiste en réexport : mêmes
noms, même texte, même empreinte. Le texte de la phase 1 est **déplacé, pas
réécrit** — le modifier changerait son empreinte et orphelinerait tout
l'historique des `ai_run` qui la référencent.

---

<a id="adr-054"></a>
## ADR-054 — La visibilité par espace est une politique **restrictive**, pas une seconde politique permissive

**Statut** ✅ Acceptée · Phase 4 · **Complète** [ADR-005](#adr-005)

**Contexte.** Depuis la phase 0, chaque table porte une politique RLS
`*_tenant_isolation` qui compare `account_id` au contexte de la session. Trente-cinq
politiques, éprouvées, testées table par table. La phase 4 introduit une seconde
frontière **à l'intérieur** du compte : une note sans espace doit rester privée,
y compris vis-à-vis d'un collègue du même compte.

Le réflexe est d'ajouter une politique de plus. **C'est le piège.** PostgreSQL
combine les politiques *permissives* par `OR` : une seconde politique permissive
sur `entry` aurait **élargi** l'accès — n'importe quelle ligne satisfaisant l'une
*ou* l'autre serait devenue visible. On aurait écrit une politique de partage en
croyant écrire une politique d'isolation, et le comportement nominal ne l'aurait
pas révélé : tout aurait *marché*, en montrant trop.

**Décision.** Les politiques de visibilité par espace sont déclarées
`AS RESTRICTIVE`. PostgreSQL les combine par `AND` avec les permissives : une
ligne doit satisfaire l'isolation de compte **et** la visibilité d'espace.
Aucune des trente-cinq politiques existantes n'est touchée.

```sql
CREATE POLICY entry_workspace_visibility ON entry AS RESTRICTIVE
    USING (
        current_user_id() IS NULL
        OR user_id = current_user_id()
        OR (workspace_id IS NOT NULL AND EXISTS (
              SELECT 1 FROM workspace_member wm
              WHERE wm.workspace_id = entry.workspace_id
                AND wm.user_id = current_user_id()))
    );
```

**La visibilité des commentaires est dérivée de celle de l'entrée**, pas
recopiée. Deux politiques indépendantes finiraient par diverger, et le jour où
elles divergent un commentaire est lisible sur une note qui ne l'est pas.

**Alternative écartée.** Filtrer dans le service applicatif. Rejetée pour la
raison qui a fondé ADR-005 : un filtre applicatif est une convention, qu'une
requête oubliée contourne sans bruit. Le seul endroit où l'isolation est vraie
plutôt que promise est la base.

**Coût accepté — et il est explicite.** La première clause,
`current_user_id() IS NULL`, fait **passer** la politique quand aucun contexte
utilisateur n'est posé. C'est une concession de compatibilité : tous les travaux
planifiés et toutes les migrations tournent sans utilisateur, et la refuser
aurait cassé chaque job du produit.

Elle a une conséquence directe : **si l'API cessait de poser `app.user_id`,
chaque organisation deviendrait un disque partagé.** La ligne qui l'empêche est
unique, dans `api/deps.py` :

```python
async with tenant_session(principal.account_id, user_id=principal.user_id) as session:
```

Un test lit le code source de `get_session` et échoue si elle disparaît
(`test_the_api_always_sets_the_user_context`). Un test qui inspecte du source est
inhabituel ; il est ici justifié parce que la propriété à garantir est *une ligne
précise à un endroit précis*, et qu'aucun test fonctionnel ne la distingue d'une
base correctement isolée par ailleurs.

Un second test vérifie que `pg_policy.polpermissive` vaut `false` — parce qu'une
politique passée par erreur en permissive élargirait l'accès sans rien changer au
comportement observable.

**Réexamen.** Si le coût de la sous-requête `EXISTS` devient mesurable sur une
grande organisation. La sortie serait une vue matérialisée d'appartenance, pas
l'abandon de la politique.

---

<a id="adr-055"></a>
## ADR-055 — Le compte *est* l'organisation

**Statut** ✅ Acceptée · Phase 4

**Contexte.** « Ajouter le multi-utilisateurs » suggère une nouvelle entité :
une organisation, qui contiendrait des comptes, qui contiendraient des
utilisateurs. C'est le modèle que la plupart des produits finissent par avoir, et
généralement au prix d'une migration douloureuse.

Or `app_user.account_id` existe depuis la phase 1 et n'a jamais interdit
plusieurs utilisateurs par compte. Rien dans le schéma ne supposait un utilisateur
unique : c'est le produit qui n'en créait qu'un.

**Décision.** Aucune entité « organisation ». Une organisation est un `account`
avec `kind = 'org'`. La frontière de locataire reste `account_id`, donc les
trente-cinq politiques d'isolation, les index, les travaux inter-locataires et le
`tenant_session` de la phase 1 fonctionnent inchangés.

Conséquence visible dans l'API : **aucune route de la phase 4 ne prend
d'identifiant de compte**. Le locataire vient du jeton, comme avant.

**Alternative écartée.** Une table `organization` avec `account.organization_id`.
Elle aurait ajouté un niveau à chaque politique RLS, à chaque index composite et à
chaque requête — pour représenter une relation qui, dans ce produit, est toujours
un-à-un. Un niveau de hiérarchie qui n'a jamais plus d'un enfant est un niveau qui
n'existe que pour être traversé.

**Coût accepté.** Une personne appartient à **un** compte. Un consultant
travaillant pour trois organisations aura trois comptes et trois sessions, ce qui
est une friction réelle. Le sortir demanderait une table d'appartenance
`(user, account)` et la révision de la notion de contexte de session dans son
entier — un chantier, pas un ajustement.

Ce coût est accepté parce que l'alternative le paie d'avance et pour tout le
monde : chaque requête du produit porterait la complexité multi-comptes pour
servir une minorité d'utilisateurs qui n'existe pas encore.

**Réexamen.** Au premier client qui exige le multi-appartenance par écrit. Le
signal sera commercial, pas technique.

---

<a id="adr-056"></a>
## ADR-056 — Un conflit de synchronisation est classé, jamais résolu tout seul

**Statut** ✅ Acceptée · Phase 4

**Contexte.** Dès qu'une donnée existe des deux côtés d'une synchronisation, elle
peut changer des deux côtés entre deux passages. Le comportement quasi universel
est le dernier-qui-écrit-gagne, souvent sans le dire.

**Décision.** `resolve()` compare quatre valeurs — l'empreinte locale, l'empreinte
distante, et les deux empreintes connues à la dernière synchronisation — et
retourne une classification :

| Résolution | Situation | Action |
| --- | --- | --- |
| `NOOP` | Rien n'a changé | — |
| `PULL` | Le distant seul a changé | Appliquer |
| `PUSH` | Le local seul a changé | Envoyer |
| `CONFLICT` | **Les deux** ont changé | Signaler, ne rien écrire |

```python
if local_changed and remote_changed:
    return SyncOutcome(Resolution.CONFLICT,
                       "modifié des deux côtés depuis la dernière synchronisation")
```

Trois des quatre cas sont automatiques. Le quatrième attend une décision humaine,
exposée par `GET /v1/integrations/conflicts`.

**Alternative écartée.** Le dernier-qui-écrit-gagne, éventuellement arbitré par
un horodatage. Rejetée parce que l'horodatage d'un service tiers n'est pas
comparable au nôtre — fuseaux, granularité, horloges non synchronisées — et
surtout parce que le cas où les deux côtés ont changé est précisément celui où
**les deux versions comptaient pour quelqu'un**. Choisir sans le dire perd du
travail en silence, ce qui est la pire des façons d'en perdre.

**Coût accepté.** Un conflit non tranché **bloque** l'élément : il ne se
synchronise plus tant que personne ne décide. Sur une intégration très active,
une liste de conflits peut s'accumuler et devenir une corvée. C'est assumé : une
corvée visible vaut mieux qu'une perte invisible.

**Coût connexe.** L'échec répété est traité séparément, et différemment. Le délai
entre tentatives croît exponentiellement, plafonné à une heure, et le
planificateur abandonne après six échecs consécutifs — parce qu'un jeton révoqué
ne redeviendra jamais valide, et que retenter éternellement une opération qui ne
peut pas réussir consomme du quota chez le fournisseur et masque le vrai
problème. `expired` et `error` sont donc deux états distincts : le premier
n'est jamais retenté.

**Réexamen.** Si le taux de conflits mesuré dépasse quelques pour cent des
éléments. Ce serait le signe que le découpage des données synchronisées est trop
grossier, pas que la politique est mauvaise.

---

<a id="adr-057"></a>
## ADR-057 — Un seul port pour sept connecteurs, dont un qui n'est pas un service

**Statut** ✅ Acceptée · Phase 4 · **Reprend** [ADR-045](#adr-045)

**Contexte.** Sept intégrations demandées : Google Calendar, Outlook, Microsoft
To Do, Slack, Teams, Notion, Obsidian. Elles n'ont ni le même protocole, ni le
même sens de circulation, ni même la même nature — Obsidian est un dossier sur un
disque.

**Décision.** Un port unique, `SyncConnectorPort`, avec `pull()` et `push()`, et
des propriétés déclarées par le fournisseur plutôt que devinées par l'appelant :
`is_server_side`, `kind`, `supports_two_way`. Le service de synchronisation ne
connaît que le port ; il ne contient aucun `if provider == …`.

**Deux conséquences qui valident la forme.**

*Outlook et Microsoft To Do partagent un adaptateur.* Microsoft Graph sert le
calendrier et les tâches depuis la même API et le même jeton. Deux fournisseurs
distincts côté produit — l'utilisateur connecte l'un sans l'autre — un seul
client HTTP côté infrastructure.

*Obsidian déclare `is_server_side = False`.* Son `pull()` lève une exception, et
son `push()` rend du Markdown avec un en-tête YAML sans faire la moindre E/S. Ce
n'est pas un cas particulier bricolé : c'est une propriété déclarée que le
planificateur consulte, et un connecteur non serveur n'est jamais programmé. Un
`if provider == "obsidian"` dans le planificateur aurait été le début de la fin de
l'abstraction.

**Alternative écartée.** Deux hiérarchies, « connecteurs de calendrier » et
« connecteurs de notification ». Rejetée parce que Microsoft To Do est
bidirectionnel et n'est ni l'un ni l'autre, et parce que le pull/push est
exactement le même mécanisme d'idempotence dans les deux cas.

**Coût accepté — et il est élevé.** Le port a été conçu contre des documentations,
**pas contre des serveurs**. Aucun jeton n'a jamais été échangé, aucun appel
réel n'a jamais été passé. Il faut s'attendre à ce que plusieurs adaptateurs
soient faux — pagination, format de date, sémantique d'`etag`. Le pari est que
le *port* survivra et que seuls les adaptateurs seront réécrits ; c'est
précisément ce que l'abstraction est censée acheter, et cela reste à vérifier.

**Réexamen.** À la première intégration réelle. Si le port doit changer pour
accueillir un vrai fournisseur, la forme est mauvaise et il vaut mieux le savoir
au septième connecteur qu'au vingtième.

---

<a id="adr-058"></a>
## ADR-058 — Les jetons sont chiffrés avec un trousseau versionné, pas une clé

**Statut** ✅ Acceptée · Phase 4

**Contexte.** Les jetons OAuth des intégrations sont des identifiants de longue
durée donnant accès à l'agenda et aux messages de l'utilisateur chez un tiers.
Les stocker en clair fait d'une fuite de sauvegarde une compromission de tous les
comptes Google des utilisateurs.

Le réflexe est une variable `ENCRYPTION_KEY`. Elle a un défaut qui n'apparaît
qu'un an plus tard : **on ne peut pas en changer**. La rotation exige de
déchiffrer tout l'existant avec l'ancienne et de rechiffrer avec la nouvelle,
donc une fenêtre pendant laquelle les deux doivent coexister — que le format ne
permet pas d'exprimer. En pratique, la rotation n'a jamais lieu.

**Décision.** AES-256-GCM, et un **trousseau** plutôt qu'une clé :

```
MINDFLOW_TOKEN_ENCRYPTION_KEYS="2026-08:AbC…=,2025-11:XyZ…="
```

La première clé est active pour les écritures ; toutes servent en lecture. Le
chiffré porte l'identifiant de la clé qui l'a produit :

```
v1$2026-08$base64(nonce ‖ scellé)
```

**L'identifiant de clé est authentifié comme donnée associée (AAD).** Le
modifier ne permet pas de faire déchiffrer un jeton par une autre clé : cela fait
échouer la vérification. Sans cela, l'identifiant serait un champ que l'on peut
réécrire dans la base pour orienter le déchiffrement.

**Une rotation se fait donc sans fenêtre de maintenance** : ajouter la nouvelle
clé en tête, garder l'ancienne, laisser un job repasser sur les lignes. L'ancienne
se retire quand plus aucune ligne ne la nomme.

**Alternative écartée.** `pgcrypto` et le chiffrement en base. Rejeté parce que
la clé finirait dans une chaîne de connexion ou une fonction SQL, donc dans le
même endroit que les données — ce qui annule l'essentiel du bénéfice.

**Coût accepté.** La perte d'une clé rend ses jetons irrécupérables ; les
utilisateurs doivent reconnecter. C'est le comportement correct. Un chiffrement
dont on peut récupérer la clé perdue est un chiffrement dont un attaquant peut
récupérer la clé.

Second coût : le service **refuse de démarrer** en production sans clé. Le
contrôle de configuration échoue au lancement plutôt que de choisir un défaut.
Un défaut silencieux ici signifierait des jetons en clair sans que personne ne
s'en aperçoive.

**Note connexe : les jetons de partage ne sont pas chiffrés, ils sont hachés.**
Le serveur n'a jamais besoin de les relire — il vérifie qu'un jeton présenté
correspond. Un condensat SHA-256 suffit, et il est strictement meilleur : une
fuite de base ne peut pas être renversée en liste de liens ouvrables. Le
plaintext est retourné exactement une fois, à l'émission.

---

<a id="adr-059"></a>
## ADR-059 — Le journal d'audit est partitionné par mois, et purgé par `DROP`

**Statut** ✅ Acceptée · Phase 4

**Contexte.** `audit_log` est la seule table du schéma qui croît sans borne, n'est
jamais mise à jour et n'est presque jamais lue. Une table d'audit non gérée
finit par représenter l'essentiel du volume d'une base et par rendre chaque
sauvegarde plus lente que la précédente.

La purge naturelle — `DELETE FROM audit_log WHERE occurred_at < …` — a trois
défauts cumulatifs : elle prend un verrou long, elle ne rend pas l'espace au
système, et elle laisse une table gonflée qui demande un `VACUUM FULL` que
personne ne planifie.

**Décision.** `audit_log` est partitionnée par `RANGE (occurred_at)`, une
partition par mois. La rétention se fait en supprimant des partitions.

```sql
SELECT ensure_audit_partitions(3);                  -- créer d'avance
SELECT drop_audit_partitions_before('2025-01-01');  -- purger
```

`DROP` d'une partition est instantané, rend l'espace, et ne verrouille pas le
reste de la table.

**Les deux fonctions vivent dans la base, en PL/pgSQL, pas dans un job Python.**
C'est délibéré : elles doivent fonctionner même quand le worker est arrêté —
c'est-à-dire exactement au moment où personne ne regarde.

**Alternative écartée.** Une purge applicative par lots. Elle aurait fonctionné,
au prix d'un job qui doit tourner longtemps, se reprendre après interruption, et
dont l'échec est silencieux. Le partitionnement déplace le problème dans le
moteur, dont c'est le métier.

**Coût accepté — le plus vicieux du projet.** Une insertion dans une plage sans
partition **échoue**. Un mois qui arrive sans que les partitions aient été créées
d'avance fait échouer *chaque* écriture d'audit, sans aucun symptôme avant le
premier du mois, puis beaucoup d'un coup.

Trois défenses, parce qu'une seule ne suffisait pas :

1. les partitions sont créées **trois mois à l'avance** ;
2. un champ `audit_partition_ready` dans `GET /v1/admin/health` — le seul champ
   de cette réponse qui *prédit* une panne au lieu de la constater ;
3. un signal d'exploitation `audit_partition_gap`, documenté en tête des runbooks.

**Second coût, dans la migration.** PostgreSQL ne convertit pas une table simple
en table partitionnée : la table est renommée, recréée partitionnée, et les
lignes du mois courant recopiées. **Les lignes plus anciennes que la plus vieille
partition créée sont abandonnées.** Sur une installation neuve c'est instantané et
sans perte ; sur une installation en service, il faut exporter d'abord. C'est
écrit dans `Deployment.md` §5 parce que c'est la seule migration du projet qui
n'est pas anodine.

La clé primaire devient composite, `(id, occurred_at)` — PostgreSQL exige que la
clé de partitionnement en fasse partie. Aucun code du produit ne référence un
enregistrement d'audit par identifiant, donc cela ne coûte rien ici ; cela le
coûterait dans une table où quelque chose pointe vers les lignes.

---

<a id="adr-060"></a>
## ADR-060 — Un dossier de plateforme que l'on modifie n'est plus de la sortie d'outil

**Statut** ✅ Acceptée · Phase 4 · **Remplace** une décision implicite de la phase 1

**Contexte.** Depuis la phase 1, `.gitignore` excluait les six dossiers de
plateforme de Flutter, avec ce commentaire : *« ce sont des sorties d'outil,
régénérées par `flutter create` — les committer n'apporte rien et coûte un
conflit de fusion à chaque montée de SDK. »*

C'était vrai tant que personne ne les touchait. Aucun build n'avait jamais été
produit, et aucun fichier de plateforme ne contenait autre chose que ce que le
générateur avait écrit.

La phase 4 a produit les builds. Et un build utilisable exige d'éditer ces
fichiers : le titre de la fenêtre — sinon la barre de titre affiche `mindflow`
en minuscules —, la taille initiale (1280×720 est une résolution vidéo, pas une
taille de travail pour une interface à trois panneaux avec une barre latérale de
248 px), et pour le web un `index.html` qui dit quelque chose pendant le
démarrage du moteur.

**Décision.** `web/`, `linux/`, `macos/` et `windows/` sont versionnés.
`android/` et `ios/` restent ignorés.

L'incohérence apparente est le critère lui-même : **on versionne ce que l'on
modifie.** Rien dans ce projet n'a personnalisé `android/` ou `ios/`, donc
`flutter create` les reproduit à l'identique et ils restent de la sortie
d'outil. Les quatre autres portent des décisions qu'aucun générateur ne
reproduira.

**Alternative écartée.** Garder tout ignoré et appliquer les personnalisations
par un script de post-génération. Rejetée : un patch appliqué après coup se
désynchronise silencieusement du fichier qu'il patche, et l'échec se manifeste
par une application dont la fenêtre s'appelle `mindflow` — que personne ne
remarque en revue puisque le diff est vide.

**Coût accepté.** Une montée de SDK Flutter demandera un `flutter create` de
rafraîchissement et une relecture du diff sur ces quatre dossiers. C'est
exactement le conflit de fusion que la décision de la phase 1 voulait éviter ;
il est accepté parce que l'alternative est de perdre les personnalisations sans
s'en apercevoir. Un conflit visible vaut mieux qu'une régression silencieuse.

**Un dossier `linux/flutter/ephemeral/` reste ignoré** — celui-là est
véritablement régénéré à chaque build et ne contient rien qu'on écrive.

**Réexamen.** Si `android/` ou `ios/` finit par être personnalisé — une
permission, un `Info.plist`, un lien profond — il rejoint la liste, pour la même
raison.

**Amendement (échafaudage Android).** `android/` rejoint la liste des dossiers
de plateforme versionnés. Son manifeste porte les autorisations micro,
notification et redémarrage ; son fichier Gradle, le désugarage sans lequel
`flutter_local_notifications` ne compile pas. Régénérer le dossier effacerait
tout cela et laisserait une application qui se lance et refuse d'enregistrer —
précisément le mode d'échec que cette décision refuse. `ios/` reste ignoré :
rien ne l'a personnalisé, et rien ici ne peut le construire ni le vérifier.

**Le contrôle qui remplace la compilation.** Aucun APK n'a jamais été produit —
il n'y a pas de SDK Android ici et Flutter ne compile pas en croisé. À défaut,
`frontend/tool/check_android.mjs` épingle ce que le manifeste et le Gradle
doivent contenir, et échoue sur les six bonnes lignes quand on lui donne un
manifeste fraîchement régénéré. C'est une garde contre l'oubli, pas une preuve
que cela compile.

---

---

<a id="adr-061"></a>
## ADR-061 — Le stockage local est un port, et le navigateur en est une implémentation

**Statut** ✅ Acceptée · Phase 4 · **Corrige** un défaut de la phase 1

**Contexte.** La phase 1 a écrit la file de captures hors ligne avec `dart:io` :
un `File` pour l'audio, un `File` pour la file, un `File` pour les préférences.
C'était juste sur les cinq plateformes qui ont un système de fichiers.

`dart:io` **compile** pour le web et lève à l'exécution. Le build web produit en
phase 4 était donc parfaitement vert — il compilait, il s'analysait, ses 147
tests passaient — et il ne pouvait enregistrer aucune note. La seule chose pour
laquelle le produit existe.

Les tests ne pouvaient pas l'attraper : ils tournaient contre un répertoire
temporaire, donc ils testaient les quatre plateformes qui ont des fichiers et ne
disaient rien des deux qui n'en ont pas.

**Décision.** Deux ports, séparés par la taille et par l'enjeu :

| Port | Contenu | Natif | Navigateur |
| --- | --- | --- | --- |
| `BlobStore` | L'audio — des mégaoctets | Fichiers | **IndexedDB** |
| `DocumentStore` | La file et les préférences — des kilooctets | Fichiers | `localStorage` |

Sélection par import conditionnel (`if (dart.library.js_interop)`), donc rien
n'est lié dans un build natif.

**La clé est le `client_capture_id`**, qui existe déjà avant les octets
(ADR-009). Aucun appelant n'apprend jamais s'il tient un chemin, une URL de blob
ou une clé IndexedDB.

**Pourquoi pas `localStorage` pour l'audio.** Synchrone, plafonné à environ cinq
mégaoctets par origine, et il ne stocke que des chaînes — donc l'audio devrait
être en base64, un tiers plus lourd. Une capture de dix minutes à 32 kbps fait
2,4 Mo, 3,2 Mo encodée : la première remplirait presque le quota et la seconde
lèverait. Une file qui contient un élément n'est pas une file.

**Pourquoi pas simplement garder l'URL de blob.** `AudioRecorder.stop()` en rend
une, ce qui est tentant et faux : l'objet qu'elle nomme meurt avec le document.
Un rechargement, un onglet tué, un Safari mis en arrière-plan un peu trop
longtemps — et la file hors ligne pointerait sur rien. Copier les octets pendant
que l'URL vit encore est tout le travail de `ingest`, et c'est pourquoi il
attend avant de rendre la main.

**Décision connexe : le format audio est porté, pas supposé.** La phase 1 codait
AAC-LC en dur, que Chrome et Firefox refusent — ils produisent de l'Opus en
WebM. Le serveur acceptait déjà les deux. `RecordingResult` et la ligne de file
portent donc le format, parce qu'une capture enregistrée dans un navigateur peut
être déclarée des semaines plus tard depuis une file qui ignore ce qui l'a
produite.

**Alternative écartée.** Empaqueter le web dans une coquille native pour
retrouver un système de fichiers. Cela règle le symptôme et abandonne la seule
chose que le web apporte : une adresse qu'on ouvre sans rien installer.

**Coût accepté.** Deux implémentations à maintenir par port, et les tests
navigateur ne s'exécutent pas dans `flutter test` — d'où `tool/smoke_web.mjs`,
qui pilote un Chromium et vérifie ce qu'aucun test unitaire ne peut voir. Sans
lui, on retomberait exactement dans le défaut que cet ADR corrige : un build
vert qui ne marche pas.

**Réexamen.** Si un jour le mode hors ligne doit conserver aussi les *notes*
consultables — le vrai chantier B4 —, `DocumentStore` sera trop petit et le
navigateur passera lui aussi à IndexedDB. Le port ne changera pas.

---

<a id="adr-062"></a>
## ADR-062 — L'analyse en direct se déclenche sur un signal, pas sur une horloge

**Statut** ✅ Acceptée · Phase 4 · **Applique** [ADR-047](#adr-047) · **Complète** [ADR-013](#adr-013)

**Contexte.** Une réunion en direct produit du texte en continu. La façon
évidente d'en tirer des actions est d'appeler un modèle à intervalle régulier —
toutes les trente secondes, disons. Sur une réunion de quarante-cinq minutes,
cela fait quatre-vingt-dix appels pour, typiquement, trois ou quatre engagements
réellement pris.

C'est le même problème qu'ADR-047, à un autre endroit : dépenser un appel là où
il n'y a rien à analyser.

**Décision.** L'analyse se déclenche sur `should_analyse`, une fonction pure :

| Condition | Effet |
| --- | --- |
| Moins de 25 mots nouveaux | Jamais |
| 70 mots nouveaux | Analyse |
| Entre les deux, avec une **phrase d'engagement** | Analyse tout de suite |
| À la clôture | Une dernière passe, quoi qu'il arrive |

Les phrases d'engagement — « on décide », « il faut que », « je m'en occupe »,
« d'ici lundi » — sont détectées sur du texte aplati (accents, apostrophes,
traits d'union), comme le routeur d'intentions de la phase 3, parce que la
dictée ne restitue pas la ponctuation de façon fiable.

**La passe de clôture n'est pas une politesse.** Les trente dernières secondes
sont le moment le plus probable pour un engagement : c'est là que les gens
conviennent de ce qui se passe ensuite.

**Décision connexe : le recollement se fait sur les mots, pas sur les
caractères.** Les blocs audio se chevauchent (ADR-013), donc une transcription
répète la couture de la précédente. `stitch` supprime la répétition — ce qui
**réécrit la fin du texte stocké**. Un décalage en caractères noté avant un
recollement pointerait au milieu d'un mot après. D'où `analysed_words`, un
compte de mots, que le recollement ne déplace jamais.

**Le plancher de recollement est un compromis assumé.** Une couture de moins de
douze caractères n'est pas supprimée : « de » est un suffixe de presque tout, et
un plancher assez bas pour l'attraper se mettrait à effacer de vrais mots. Le
coût est un léger bégaiement dans la transcription, visible et inoffensif ; le
coût inverse est un mot supprimé, invisible et faux. Un test épingle ce choix
pour qu'il reste une décision.

**Alternative écartée.** Analyser à chaque bloc. Plus simple, prévisible, et
vingt fois plus cher pour un résultat identique sur les longs passages où
personne ne décide rien — c'est-à-dire la plus grande partie d'une réunion.

**Coût accepté.** Un engagement formulé sans aucune des phrases connues, dans un
passage court, attend le seuil de mots. Le retard maximal est d'environ trente
secondes de parole, et la passe de clôture le rattrape de toute façon. La liste
de phrases est française et devra être traduite en même temps que l'interface
(E11).

**Réexamen.** Quand `meeting_analyses_total` sera mesuré en production. Le
signal à surveiller est simple : ce compteur doit croître avec le nombre
d'**engagements**, pas avec les minutes de réunion. S'il suit les minutes, la
logique de déclenchement a cessé de fonctionner et chaque réunion paie une
horloge.

---

<a id="adr-063"></a>
## ADR-063 — Le CORS est ouvert en développement, fermé par défaut ailleurs

**Statut** ✅ Acceptée · Phase 4 · **Applique** [ADR-029](#adr-029)

**Contexte.** L'API n'a émis aucun en-tête CORS pendant quatre phases. Un client
web servi sur une autre origine — c'est-à-dire tout client web pendant le
développement, où l'application est sur 8080 et l'API sur 8000 — ne pouvait donc
appeler aucune route. Le navigateur bloque la requête avant qu'elle parte : le
serveur ne voit rien, ne journalise rien, et l'application paraît cassée sans
cause visible.

Rien ne pouvait le signaler. Les 896 tests serveur parlent à l'application en
ASGI, sans origine. `flutter test` ne fait aucune requête réseau. Le test de
fumée web démarre la page et n'appelle jamais l'API. Le défaut n'est visible que
depuis un navigateur servi ailleurs que l'API — exactement la position d'un
utilisateur qui découvre le produit.

**Décision.** Trois règles.

| Environnement | Origines acceptées |
| --- | --- |
| `local`, `test` | `http://localhost:*` et `http://127.0.0.1:*`, par expression régulière |
| `staging`, `prod` | Uniquement `MINDFLOW_CORS_ALLOW_ORIGINS`, vide par défaut |
| Partout | `*` refusé au démarrage ; `allow_credentials` toujours faux |

**Pourquoi une expression régulière en développement.** Le port du client n'est
pas prévisible : `flutter run` en choisit un au hasard, `tool/serve_web.mjs` sert
sur 8080. Épingler une liste de ports ferait échouer un démarrage sur deux avec,
côté navigateur, une erreur que le serveur ne voit pas. Le motif est ancré aux
deux bouts : `localhost.attaquant.test` n'est pas `localhost`.

**Pourquoi vide par défaut en production.** Le déploiement de référence sert le
client web depuis le même hôte que l'API : il n'y a pas de requête
inter-origines, donc pas d'en-tête à émettre. N'ouvrir que ce qui est demandé
est la bonne posture, et elle est ici gratuite.

**Pourquoi `allow_credentials` est faux partout.** L'authentification passe par
un en-tête `Authorization`, jamais par un cookie (ADR-029). Rien n'est joint
automatiquement à une requête inter-origines : la question du CSRF ne se pose
pas, et l'activer n'apporterait qu'une surface.

**Pourquoi `X-Request-Id` est exposé.** Sans `expose_headers`, le JavaScript ne
peut pas le lire, et un incident signalé par un utilisateur devient impossible à
relier à un journal serveur. C'est le seul en-tête exposé.

**Alternative écartée.** `allow_origins=["*"]`. Une ligne de moins, et elle
autorise n'importe quel site à appeler l'API avec le jeton que sa page détient.
Le contrôle de configuration refuse désormais de démarrer avec.

**Coût accepté.** Un déploiement où le client web est sur un autre domaine que
l'API ne fonctionnera pas tant que `MINDFLOW_CORS_ALLOW_ORIGINS` n'est pas
renseigné. C'est un échec bruyant au premier essai, préférable à une ouverture
tacite.

**Réexamen.** Si un jour l'authentification passe par cookie — par exemple pour
un mode hors ligne prolongé —, `allow_credentials` et le CSRF redeviennent une
vraie question, et cette décision est à reprendre entièrement.

---

<a id="adr-064"></a>
## ADR-064 — Le `state` OAuth est chiffré, et ne stocke rien

**Statut** ✅ Acceptée · Phase 4 · **Complète** [ADR-056](#adr-056), [ADR-058](#adr-058)

**Contexte.** Le flux OAuth n'existait pas. `POST /v1/integrations` acceptait un
jeton *déjà obtenu*, et le `refresh_token` était chiffré, rangé en base, et
**jamais relu**. Conséquence mesurable : un jeton Google vit une heure. Passé ce
délai, le connecteur recevait un 401, la connexion passait `expired`, et
`expired` n'est jamais retenté (ADR-056). Trois des sept intégrations tenaient
donc soixante minutes.

Écrire l'échange pose deux questions dont les réponses habituelles coûtent
cher : où vivre entre la demande d'autorisation et le retour, et comment
distinguer un octroi mort d'une panne passagère.

**Décision 1 — le `state` est chiffré et porte tout.**

Il contient l'identité du demandeur, le fournisseur, l'instant d'émission et le
vérificateur PKCE. Chiffré avec le trousseau d'ADR-058, donc opaque au
navigateur et lisible de nous seuls.

| Ce qu'on évite | Pourquoi |
| --- | --- |
| Une table `oauth_request` | Une table à purger, un index, une migration, et un état qui survit à ce qu'il représente |
| Redis | Une demande d'autorisation perdue au redémarrage, pour économiser 200 octets |
| Un `state` signé | Le vérificateur PKCE y serait **lisible**, et PKCE ne protégerait plus de rien |

Le dernier point est le seul qui ne soit pas qu'une question de commodité :
signer suffit contre le rejeu, pas contre la lecture. Le vérificateur traverse
le navigateur ; il doit en sortir intact et secret.

**PKCE alors que nous sommes un client confidentiel** — nous détenons un secret
côté serveur. Cela ne coûte rien et couvre le cas où le code d'autorisation
fuite du navigateur : sans le vérificateur, il ne s'échange pas.

**Décision 2 — le renouvellement est préventif, et le 401 reste un filet.**

Le jeton est renouvelé deux minutes avant l'échéance, pas à la première erreur :
une passe qui échoue puis renouvelle a perdu son tour, et à cinq minutes de
cadence l'utilisateur le voit. Un 401 malgré tout — révocation d'appareil,
changement de mot de passe — déclenche **un** renouvellement, puis une reprise.
Une seule : boucler ici transformerait une connexion cassée en déni de service
contre le fournisseur.

Un échec de renouvellement préventif **ne fait pas échouer la passe** : le jeton
en place est encore valable, et abandonner perdrait une synchronisation qui
allait réussir. Ce point a été écrit après avoir vu un test échouer en
affirmant le contraire.

**Décision 3 — `invalid_grant` est terminal, le reste ne l'est pas.**

Un octroi révoqué ne guérit jamais ; un 503 du fournisseur d'identité, si.
Confondre les deux donne soit des reconnexions demandées pour rien, soit un
compteur d'échecs qui monte contre un jeton mort.

**Trois pièges encodés dans le code plutôt que dans une page de wiki**, parce
qu'ils coûtent chacun une demi-journée et se manifestent tous par « la
synchronisation s'est arrêtée » :

1. **Google ne rend un jeton de rafraîchissement que si on le demande** —
   `access_type=offline` *et* `prompt=consent`. Sans eux, le défaut qu'on répare
   est reproduit à l'identique, et il ne se voit qu'à la deuxième autorisation
   du même compte.
2. **Microsoft fait tourner ses jetons de rafraîchissement, pas Google.** Une
   réponse Google n'en contient aucun : écraser avec `None` casse la connexion
   au renouvellement suivant, une heure plus tard, loin de la cause.
3. **Le remplissage base64 de PKCE.** Un `=` de trop et le fournisseur répond
   `invalid_grant`, ce qui envoie chercher du côté du code d'autorisation.

**Ce qui reste hors du flux, délibérément.** Slack et Teams s'authentifient par
une URL de webhook entrant ; Notion par un jeton d'intégration interne ;
Obsidian est un dossier. Rien de tout cela n'expire. Les faire passer par OAuth
ajouterait une cérémonie sans rien résoudre — et masquerait qu'ils fonctionnent
déjà, ce qui en fait aujourd'hui les seuls connecteurs utilisables sans
enregistrer une application.

**Coût accepté.** Deux applications à déclarer chez deux fournisseurs, et une
`redirect_uri` qui doit correspondre à l'octet près — d'où sa dérivation depuis
`MINDFLOW_PUBLIC_BASE_URL` plutôt qu'une seconde variable à tenir synchronisée.

**Réexamen.** Au premier appel réel. Le flux est testé contre un serveur
d'autorisation simulé (`respx`) : les formats sont conformes aux
spécifications, aucun fournisseur ne les a jamais confirmés (`TODO.md` B8).
