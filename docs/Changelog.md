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

### Corrigé — L'API était injoignable depuis un navigateur

Aucun en-tête CORS n'était émis. Un client web servi sur une autre origine — le
cas de tout client web en développement, application sur 8080 et API sur 8000 —
ne pouvait appeler **aucune** route : le navigateur bloque la requête avant
qu'elle parte, le serveur ne voit rien, et l'application paraît cassée sans
qu'aucun journal ne le dise.

Ouvert aux origines locales en `local` et `test`, quel que soit le port ; fermé
par défaut ailleurs, où seule `MINDFLOW_CORS_ALLOW_ORIGINS` compte. `*` est
refusé au démarrage et `allow_credentials` reste faux partout —
l'authentification passe par un en-tête, jamais par un cookie (ADR-063).

### Ajouté — `tool/e2e_capture.mjs`, une capture réelle de bout en bout

Chromium, son micro synthétique, l'application servie comme un utilisateur la
servirait. Onze vérifications : contexte sécurisé, codec accepté, API joignable
depuis une autre origine, octets produits par `MediaRecorder`, téléversés,
transcrits, transformés en entrée — puis le parcours complet dans l'interface,
de la connexion à l'écran « Capture enregistrée ».

C'est la première capture micro du projet. Ce qui existait s'arrêtait juste
avant : le test de fumée web fait transiter quatre octets par IndexedDB et
n'appelle jamais l'API. Vérifié aussi en sens inverse — CORS retiré, le test
échoue sur les quatre bonnes lignes.

`serve_web.mjs` sert le build sur `127.0.0.1` : `getUserMedia` n'est accordé
qu'en contexte sécurisé, donc HTTPS ou `localhost`. Un `file://` ou une IP de
LAN en clair donnent une application qui s'ouvre et ne peut pas enregistrer un
mot.

### Corrigé — Le worker ne démarrait pas

Trouvés en démarrant la pile complète pour la première fois hors de la suite de
tests (`Deployment.md` §0). Les trois défauts sont sur le chemin de lancement,
qu'aucun test ne parcourait : la suite appelle les tâches directement.

- **`WorkerSettings.redis_settings` était une `@staticmethod`.** `arq` lit
  `WorkerSettings.__dict__` plutôt que l'attribut, reçoit le descripteur
  lui-même et meurt sur `'staticmethod' object has no attribute 'host'` avant
  la première tâche. C'est la commande du `docker-compose.yml`, jamais lancée
  faute de démon Docker pendant les quatre phases.
- **La tâche de traitement s'enregistrait sous le mauvais nom.** `arq` nomme
  d'après `__qualname__` et non `__name__` : le worker annonçait
  `process_capture_job` là où l'API met `process_capture` en file. Travail
  accepté, jamais exécuté, capture immobile en `uploaded` — et le balayeur la
  ré-enfilait sous le même mauvais nom, indéfiniment.
- **Le worker écoutait la mauvaise file.** L'API écrit sur `capture.realtime`
  (`ArqQueue.connect`), le worker écoutait la file par défaut d'`arq`. Même
  silence, un étage plus bas.

`tests/unit/test_worker_settings.py` passe désormais par `arq.worker.get_kwargs`
— le chargeur d'`arq` lui-même — au lieu de contourner le point de départ.

### Ajouté — `mindflow/tool/dev_up.sh`

Démarrer le produit sur une machine de développement, en une commande. Crée le
rôle et la base, pose `pgvector`, applique les neuf migrations, démarre le
worker **puis** l'API, et ne rend la main qu'après avoir vu `/health` répondre
et le worker annoncer ses tâches.

Les deux vérifications sont le point du script : un worker mort laisse une API
qui accepte chaque capture et n'en traite aucune, sans lever la moindre erreur.
C'est exactement ce qui a été vécu ci-dessus, et un script de démarrage qui
rend la main sans avoir rien démarré est pire que pas de script du tout.

Idempotent, et explicite sur ce qui manque : PostgreSQL absent, superutilisateur
injoignable, `pgvector` non installé et Redis absent donnent chacun un message
qui dit quoi faire, pour Debian, Homebrew et Docker.

### Documentation

- ADR-063 : le CORS, ouvert en développement et fermé par défaut ailleurs.
- `mindflow/README.md` : comment faire tourner le produit, ce que les moteurs
  `fake` valent, et ce qui n'a jamais tourné.
- `Deployment.md` §0 : la marche à suivre pour faire tourner le produit en
  local, exécutée le 2026-08-05 et non rédigée d'avance. Capture déclarée,
  téléversée, transcrite, transformée en entrée, retrouvée dans le tableau de
  bord — sans clé d'API, sans Docker, sans Supabase, et en disant ce que cela
  ne prouve pas.

---

## [0.6.0] — 2026-08-04

**L'IA en réunion.** La table `meeting_session` existait depuis la 0.5.0 et
n'était remplie par rien. 892 tests côté serveur, 166 côté client.

### Ajouté — Domaine (`domain/meeting.py`)

Trois problèmes, trois fonctions pures, aucune E/S — ce qui est la seule façon
de tester cette fonctionnalité du tout : l'alternative demanderait un micro, un
fournisseur de parole et quarante-cinq minutes.

- **Recollement.** Les blocs audio se chevauchent (ADR-013), donc une
  transcription répète la couture de la précédente. `stitch` trouve le plus long
  suffixe de ce qu'on a qui soit aussi un préfixe de ce qui arrive.
- **Déclenchement.** `should_analyse` : jamais sous 25 mots nouveaux, toujours
  au-delà de 70, et immédiatement sur une **phrase d'engagement** (« on décide »,
  « je m'en occupe », « d'ici lundi »). Détectées sur du texte aplati, comme le
  routeur d'intentions de la phase 3, parce que la dictée ne restitue pas la
  ponctuation.
- **Déduplication.** L'extraction incrémentale repropose ce qu'elle a déjà
  proposé ; une liste qui se répète est une liste que personne ne lit jusqu'au
  bout.

39 tests unitaires sur ces trois fonctions seules.

### Ajouté — Prompts, service, API, écran

- `meeting_live` et `meeting_summary`. Le premier a pour instruction principale
  de **ne rien renvoyer** quand rien n'a été décidé — le cas le plus fréquent.
- `MeetingService`, avec un contrat de dégradation plus strict que le reste du
  produit (voir ci-dessous).
- Neuf routes (`API.md` §18), dont un flux SSE pour un second écran.
- Un écran de réunion : chronomètre, panneau en direct, compte rendu.
- Migration 0009 : `analysed_words` et un index partiel sur les réunions en
  cours.

### Le contrat de dégradation

**Une fonctionnalité en direct se dégrade en enregistrement, jamais en panne.**
Quelqu'un est dans une pièce avec d'autres gens ; la réunion ne s'interrompt pas
pour attendre notre fournisseur.

| Ce qui échoue | Ce qui se passe |
| --- | --- |
| La transcription d'un bloc | Un trou, le bloc suivant arrive quand même |
| Une analyse | `analysed_words` n'avance pas : la fenêtre est réessayée |
| Un refus du modèle | La fenêtre avance : la réessayer serait refusée à l'identique |
| Le compte rendu final | Rapport **dégradé** : ce que la passe en direct avait trouvé, et il le dit |

Les blocs perdus sont **affichés**. Une transcription trouée produit un compte
rendu confiant et incomplet, et seule la personne présente peut juger si cela
compte.

### Décisions

- [ADR-062] L'analyse en direct se déclenche sur un signal, pas sur une horloge

Une horloge à trente secondes ferait quatre-vingt-dix appels sur une réunion de
trois quarts d'heure, pour trois ou quatre engagements réellement pris. C'est
ADR-047 appliqué à un autre endroit.

### Un compromis épinglé par un test

Une couture de moins de douze caractères n'est pas supprimée : « de » est un
suffixe de presque tout, et un plancher assez bas pour l'attraper effacerait de
vrais mots. Le coût est un léger bégaiement — visible et inoffensif — contre un
mot supprimé, invisible et faux. Un test fixe ce choix pour qu'il reste une
décision plutôt qu'un oubli.

### Ce qui reste ouvert

- **Aucune réunion réelle n'a été transcrite** (B17). Le service est testé contre
  un transcripteur et un modèle scriptés ; les seuils de recollement sont réglés
  sur des chevauchements supposés.
- Le client ne consomme pas encore le flux SSE : il reçoit ses suggestions sur
  la réponse de chaque bloc, ce qui suffit à l'appareil qui enregistre (B15).
- Les phrases de déclenchement sont françaises (B16).

**De la liste d'origine de la phase 4, il ne reste que B4** : le mode hors ligne
au-delà de la capture.

---

## [0.5.4] — 2026-08-04

**Le web peut capturer.** La 0.5.3 livrait un build web qui compilait,
s'analysait, passait ses tests — et ne pouvait enregistrer aucune note, c'est-à-
dire faire la seule chose pour laquelle le produit existe. 152 tests, et une
vérification qui exécute réellement la page.

### Corrigé — le stockage local (ADR-061)

La phase 1 avait écrit la file hors ligne avec `dart:io` : un `File` pour
l'audio, un pour la file, un pour les préférences. `dart:io` **compile** pour le
web et lève à l'exécution — d'où un build entièrement vert et entièrement
inutilisable.

Deux ports remplacent les trois usages, séparés par la taille et par l'enjeu :

| Port | Contenu | Natif | Navigateur |
| --- | --- | --- | --- |
| `BlobStore` | L'audio — des mégaoctets | Fichiers | **IndexedDB** |
| `DocumentStore` | La file et les préférences | Fichiers | `localStorage` |

`localStorage` pour l'audio aurait été plus simple et faux : plafonné à cinq
mégaoctets, en base64 donc un tiers plus lourd, une capture de dix minutes
remplirait presque le quota et la deuxième lèverait. Garder l'URL de blob
l'aurait été davantage : l'objet qu'elle nomme meurt avec le document, donc la
file aurait pointé sur rien après un rechargement.

### Corrigé — trois défauts que seule l'ouverture de la page révèle

Aucun n'était visible dans `flutter build`, `flutter analyze` ni les tests.

- **Le moteur de rendu était chargé depuis `gstatic.com`** au démarrage. Une
  application dont le sujet est de fonctionner sans réseau ne peut pas commencer
  par télécharger 19 Mo chez un tiers. `--no-web-resources-cdn`.
- **La police par défaut était chargée depuis `fonts.gstatic.com`.** Quand cet
  appel échoue, l'interface s'affiche **sans aucun texte** — pas une police de
  repli, rien. Roboto est désormais empaquetée (512 ko).
- **L'écran de démarrage n'était retiré par personne.** Le commentaire que
  j'avais écrit affirmait que le moteur s'en chargeait ; c'est faux, il ajoute sa
  vue et laisse le reste du document tel quel. L'application tournait dessous.

### Corrigé — le codec audio

`AAC-LC` était codé en dur. Chrome et Firefox le refusent ; ils produisent de
l'Opus en WebM, que le serveur acceptait déjà. Le format est maintenant choisi
par plateforme **et porté** par la ligne de file, parce qu'une capture
enregistrée dans un navigateur peut être déclarée des semaines plus tard.

### Corrigé — une panne réseau ne se lisait pas comme telle

`ApiException.fromDio` existait depuis la phase 1, était testée, et n'était
appelée par rien : un échec de transport s'échappait en `DioException` brut et
tombait dans le `catch` générique. Un téléphone dans un tunnel affichait donc
« l'envoi a échoué » au lieu de « pas de réseau, la capture est conservée » — le
seul message que la file hors ligne existe pour rendre vrai. Les échecs de
transport sont désormais traduits en document de problème par l'intercepteur,
donc chaque appelant les traite déjà.

### Ajouté — `tool/smoke_web.mjs`

Sert le bundle, l'ouvre dans un Chromium, **coupe le réseau et recharge**.
Vérifie que l'application démarre sans réseau, qu'aucun écran de démarrage ne
reste, que le texte s'affiche, et que l'audio en file survit à la coupure.
Câblé dans la matrice CI.

C'est la seule vérification du projet qui atteste que le mode hors ligne existe.
Les quatre défauts ci-dessus sont l'argument : quatre gates verts, un produit
qui ne marchait pas.

### Décisions

- [ADR-061] Le stockage local est un port, pas `dart:io`

### Ce qui reste de B4

L'application démarre sans réseau et la file de captures survit à la coupure.
Elle ne conserve **pas** les notes déjà écrites pour consultation hors ligne :
cela demande un miroir local et une file de mutations sortantes, pas une couche
de stockage. Celle-ci existe désormais et servira de base (`RoadmapV2.md` §6).

---

## [0.5.3] — 2026-08-04

**Le client se compile.** Jusqu'ici il n'avait jamais été compilé pour aucune
cible : le projet ne contenait aucun dossier de plateforme. 147 tests Flutter
inchangés.

### Ajouté

- Dossiers de plateforme `web/`, `linux/`, `macos/`, `windows/`, générés puis
  personnalisés — titre de fenêtre, taille initiale, écran de démarrage web.
- `tool/build.sh`, un script par cible, qui **refuse** une cible que l'hôte ne
  peut pas produire plutôt que de laisser lire une erreur de chaîne d'outils.
- Matrice CI à quatre entrées, un exécutant par système.
- Écran de démarrage web : un bundle Flutter met plusieurs secondes à démarrer
  sur un cache froid, et une page blanche pendant trois secondes est
  indiscernable d'un déploiement cassé.

| Cible | État |
| --- | --- |
| **Web** | ✅ Compilé, servi et vérifié (26 Mo) |
| **Linux** | ✅ Compilé, binaire ELF vérifié, aucune bibliothèque manquante (27 Mo) |
| **Windows** | ⚠️ Scaffoldé et câblé en CI, **jamais compilé** |
| **macOS** | ⚠️ Idem |

**Windows et macOS ne sont pas « à faire », ils sont « impossibles ici ».**
Flutter édite les liens contre le SDK de la plateforme ; il n'y a pas de
compilation croisée, et aucun hôte Windows ou macOS n'était disponible.

### Corrigé

- **Le build Linux ne compilait pas**, et la cause était en amont.
  `record 5.2.1` sous-contraint ses propres implémentations : il accepte
  `record_platform_interface ^1.2.0` à côté de `record_linux >=0.5.0 <1.0.0`, et
  les plus récents des deux ne s'assemblent pas — `record_linux 0.7.2`
  implémente l'interface telle qu'elle était en 1.2, 1.3 a ajouté un argument
  nommé à `hasPermission`, 1.5 a ajouté `startStream` et `streamBufferSize`.
  Résoudre au plus récent produit soit un plugin Linux auquel il manque des
  membres abstraits, soit un plugin web qui lit un champ inexistant.

  Il existe exactement un jeu cohérent sous Flutter 3.27, et il est désormais
  épinglé avec de **vraies contraintes** plutôt qu'un `dependency_overrides` :
  un override tait les contraintes des autres paquets au lieu de les satisfaire,
  donc il aurait réparé Linux en laissant le web cassé — silencieusement.

  Coût accepté : le module d'enregistrement reste à son niveau de 2024 sur
  toutes les plateformes. Le débloquer demande `record ^7`, qui demande
  Flutter ≥ 3.44.8.

### Modifié

- `.gitignore` : les quatre dossiers de plateforme personnalisés sont désormais
  versionnés (ADR-060). `android/` et `ios/` restent ignorés — rien ne les a
  personnalisés, donc `flutter create` les reproduit à l'identique.

### Décisions

- [ADR-060] Un dossier de plateforme que l'on modifie n'est plus de la sortie
  d'outil

### Ce que le build web révèle, et qui n'est pas une bonne nouvelle

**Le web ne peut pas capturer.** Le client utilise `dart:io` pour la file de
captures locale ; sur le web cette bibliothèque compile et lève à l'exécution.
Le web sert donc à consulter, chercher et interroger — pas à enregistrer une
note vocale, c'est-à-dire pas à faire la chose pour laquelle le produit existe.
Ce n'est pas un réglage à corriger mais une limite à traiter dans le chantier
hors ligne (`TODO.md` B4).

### Ouvert par cette version

- Aucune signature de code ni notariat : un `.app` non notarié est refusé par
  Gatekeeper, un `.exe` non signé déclenche SmartScreen (B13).
- La matrice CI desktop est écrite et n'a jamais tourné (B6).

---

## [0.5.2] — 2026-08-04

**La synchronisation devient automatique.** C'était le dernier écart entre ce
qui avait été demandé en phase 4 et ce qui tournait : les connecteurs, le port,
la classification des conflits et l'écran fonctionnaient tous, et personne ne
les déclenchait. 826 tests.

### Ajouté — `sync_job`

- Toutes les cinq minutes, inter-locataires. La connexion privilégiée
  **sélectionne des identifiants et rien d'autre** ; tout le travail se fait
  dans une session locataire avec le contexte utilisateur posé, donc chaque
  écriture passe par une politique, y compris les restrictives d'ADR-054.
- `is_due` est une **fonction pure** et constitue toute la politique
  d'ordonnancement — le reste du job est de la plomberie. 18 tests unitaires
  sur elle seule.

| Situation | Décision |
| --- | --- |
| Jamais synchronisée | Due immédiatement |
| Saine | Due après cinq minutes |
| En échec | Retard exponentiel, plafonné à une heure |
| Six échecs consécutifs | **Jamais.** Seule une reconnexion remet le compteur à zéro |
| `expired` | **Jamais sélectionnée.** Un grant révoqué ne guérit pas d'un réessai |
| Obsidian | **Jamais sélectionnée** — `is_server_side = false` |

- Le filtre de fournisseurs est **dérivé de `Provider.is_server_side`**, pas
  énuméré : un nouveau connecteur n'a pas à penser à s'y ajouter.
- Un tick est borné à quarante connexions et sert **la plus ancienne d'abord**,
  pour qu'un retard s'écoule dans l'ordre qui fait le moins de mal.
- L'échec d'une connexion ne termine pas le tick. `IntegrationService.sync` ne
  lève déjà pas pour une panne fournisseur, mais un bug dans un adaptateur ne
  doit pas coûter leur passage aux six autres.

**Le retard d'une connexion en échec se calcule sur `updated_at`**, pas sur
`last_sync_at` : un échec ne met délibérément pas à jour `last_sync_at`, parce
que cette colonne signifie « dernier moment où nous étions en phase avec le
fournisseur » et un échec ne nous y a pas mis. L'imprécision est réelle et
énoncée plutôt que masquée — une modification de la connexion par l'utilisateur
touche aussi `updated_at` et peut retarder d'une heure au plus un réessai. C'est
le prix accepté pour ne pas ajouter une colonne dont cette ligne serait le seul
lecteur.

### Tests

- 18 unitaires sur `is_due`, 15 d'intégration sur le passage complet.
- Dont un qui inspecte le source du job pour vérifier que le bloc privilégié ne
  contient que le `SELECT`. Inhabituel, et justifié pour la même raison que
  `test_the_api_always_sets_the_user_context` : aucun test fonctionnel ne
  distingue un job qui écrit via une session locataire d'un job qui écrit
  privilégié — les deux produisent les bonnes lignes sur un jeu de test
  mono-locataire.

### Ce qui reste ouvert

Trois lignes, et aucune n'est un module : IA temps réel en réunion, mode hors
ligne au-delà de la capture, builds Desktop et Web (`TODO.md` §6 ter).

**Le risque le plus sous-estimé change de nature.** `sync_job` déclenche
désormais sept adaptateurs qui n'ont jamais parlé à un vrai serveur. Le job est
testé contre un connecteur bouchon ; ce qu'il déclenchera en production reste
inconnu, et ADR-057 en assume explicitement le coût.

---

## [0.5.1] — 2026-08-04

**Ce que la phase 4 avait laissé de côté.** Deux des six manques énoncés dans
la 0.5.0 sont traités : le job de partitionnement, et les écrans qui rendent
l'API d'entreprise utilisable. 793 tests côté serveur, 147 côté client.

### Ajouté — `partition_job`

- Quotidien à 03:11, **et au démarrage du worker** — ce dernier couvre le cas
  où le worker a été arrêté au passage d'un mois, c'est-à-dire exactement quand
  personne ne regardait.
- Appelle `ensure_audit_partitions` puis, si une rétention est configurée,
  `drop_audit_partitions_before`. Les deux fonctions vivaient déjà en base et
  n'étaient appelées par rien.
- `MINDFLOW_AUDIT_RETENTION_MONTHS` vaut **0 par défaut : la purge est
  désactivée**. Supprimer de l'historique d'audit parce que personne n'a
  configuré de rétention est un échec pire qu'une table qui grossit ; un `DROP`
  irréversible doit être demandé, jamais subi.
- Deux jauges, `audit_partitions` et `audit_partition_gap`, **relues depuis
  `pg_class`** après chaque passage plutôt que déduites du travail que le job
  croit avoir fait. Une création qui n'a silencieusement rien fait doit
  apparaître.
- 16 tests, dont un qui n'exerce aucun de nos codes : il épingle le fait qu'une
  insertion dans une plage sans partition **échoue** côté PostgreSQL. C'est le
  comportement dont tout ADR-059 découle, et le découvrir par des notes de
  version serait une mauvaise façon de l'apprendre.

### Ajouté — Écrans d'entreprise (Flutter)

- **Espaces** : liste, création, archivage, membres et rôles d'espace.
- **Équipe** : membres du compte, invitations, liens partagés — trois listes sur
  un écran parce qu'elles répondent à une seule question, *qui peut voir quoi ?*
- **Mentions** : séparé du centre de notifications, parce qu'une mention est la
  seule notification qu'on veut garder en coupant les autres.
- **Intégrations** : les sept services, leur état, et les conflits.
- **Administration** : vue d'ensemble, journal d'audit, usage, et les deux
  alertes opérationnelles.
- **Commentaires** et **feuille de partage**, montés sur le détail d'une note.
- 39 tests : 28 sur les modèles, 11 sur les écrans.

Trois comportements de l'interface sont testés parce qu'ils sont des phrases
qu'on pourrait supprimer sans qu'aucun test ne rougisse : l'écran vide des
espaces énonce qu'une note hors espace est privée ; Obsidian n'a **pas** de
bouton « Synchroniser » ; un accès révoqué se voit proposer « Reconnecter » et
jamais « Réessayer ».

### Corrigé

Deux bugs réels, trouvés par les tests d'écran et invisibles à la lecture.

- `ShareSheet.dispose` lisait `ref` après démontage. Le nettoyage du jeton en
  clair ne s'exécutait donc **jamais**, et l'exception était avalée par le
  framework. Le contrôleur est désormais capturé pendant que le widget est
  vivant.
- La carte de conflit mettait ses deux choix dans un `Row` : sur un téléphone,
  l'un des deux était rogné. Un conflit dont une seule issue est visible est
  exactement ce qu'ADR-056 refuse.

### Ce qui reste ouvert

- **`sync_job` n'existe toujours pas.** La synchronisation n'a lieu que sur
  appel explicite de `POST /v1/integrations/{id}/sync` : la « synchronisation
  automatique » demandée en phase 4 attend un clic.
- IA temps réel en réunion, mode hors ligne au-delà de la capture, builds
  Desktop et Web, notifications intelligentes : inchangés (`TODO.md` §6 ter).

---

## [0.5.0] — 2026-08-03

**Phase 4 — Les fonctionnalités d'entreprise.** Le produit passe d'un outil
personnel à un outil d'équipe. **Rien de l'existant n'a été réécrit** : les 35
politiques d'isolation de compte, les prompts de la phase 3 et leurs empreintes,
et l'intégralité des tests antérieurs sont inchangés. 777 tests passent.

### Ajouté — Domaine

- `permissions` : quatre rôles de compte (`owner`, `admin`, `member`, `viewer`)
  et trois rôles d'espace (`editor`, `commenter`, `reader`), ordonnés. `can()`
  est une **fonction totale** : une action inconnue est refusée, jamais autorisée
  par omission.
- `collaboration` : analyse des `@mentions` — avec un `lookbehind` négatif qui
  refuse les adresses de courriel —, émission et vérification des jetons de
  partage. La révocation est vérifiée **avant** l'expiration, parce que c'est ce
  que l'auteur du lien a fait.
- `sync` : classification des synchronisations en `NOOP`, `PULL`, `PUSH`,
  `CONFLICT`, sans aucune E/S. Délai entre tentatives exponentiel, plafonné à
  une heure, abandon après six échecs consécutifs.

### Ajouté — Infrastructure

- `infra/crypto` : AES-256-GCM avec **trousseau versionné**. Format
  `v1$id$base64(nonce‖scellé)`, l'identifiant de clé authentifié comme donnée
  associée. La rotation se fait sans fenêtre de maintenance.
- `infra/sync/connectors` : sept fournisseurs derrière un port unique. Outlook et
  Microsoft To Do partagent un adaptateur Microsoft Graph. Obsidian déclare
  `is_server_side = false` et ne fait aucune E/S serveur.
- Neuf tables : `workspace`, `workspace_member`, `invitation`, `comment`,
  `mention`, `share_link`, `integration_connection`, `external_link`,
  `meeting_session`.

### Ajouté — API

- Espaces, membres, invitations, commentaires, mentions, partage, intégrations,
  conflits (`API.md` §16).
- `/v1/admin/overview`, `/audit`, `/usage`, `/health` (`API.md` §17).
- `GET /v1/shared/{token}` : la **seule** route non authentifiée du produit. Elle
  s'exécute sur une connexion de maintenance et retourne une entrée, par
  identifiant.
- `permission_denied` (403), distinct de `forbidden` : une portée de jeton
  insuffisante et un rôle insuffisant appellent des remèdes différents.

### Sécurité

- **Deux politiques RLS `RESTRICTIVE`** sur `entry` et `comment`. Restrictives et
  non permissives : PostgreSQL combine les permissives par `OR`, donc une seconde
  politique permissive aurait **élargi** l'accès en croyant le restreindre.
- Une note sans espace est privée, y compris pour l'administrateur du compte —
  appliqué par la base, pas par l'API.
- Jetons OAuth chiffrés au repos ; jetons de partage stockés **hachés** en
  SHA-256 et retournés en clair exactement une fois.
- Le service refuse de démarrer en production sans clé de chiffrement, et refuse
  une `PUBLIC_BASE_URL` en `localhost` — qui ferait pointer chaque lien de
  partage sur la machine de l'émetteur.
- Aucun endpoint inter-comptes, aucun « super administrateur ». C'est une absence
  délibérée (`API.md` §17.1).

### Modifié

- `audit_log` est **partitionnée par mois**. Clé primaire composite
  `(id, occurred_at)`. Rétention par `DROP TABLE`.
- Sept index ajoutés, chacun motivé par une requête existante (`Database.md`
  §16.5).
- `NotificationKind` gagne `mention` et `comment`, distincts de `system` : une
  mention est la notification qu'on veut garder en coupant les autres.

### Corrigé

- **Défaut latent de la phase 2** : la migration 0003 n'avait jamais posé
  `ALTER DEFAULT PRIVILEGES` pour `mindflow_maintenance`, rendant invisible à
  tous les travaux inter-locataires **chaque table créée après elle**. Le défaut
  était silencieux — un job qui ne voit rien ne lève pas d'erreur, il ne fait
  rien. Rattrapé en 0006 et 0007.

### Décisions

- [ADR-054] La visibilité par espace est une politique **restrictive**
- [ADR-055] Le compte *est* l'organisation
- [ADR-056] Un conflit de synchronisation est classé, jamais résolu tout seul
- [ADR-057] Un seul port pour sept connecteurs, dont un qui n'est pas un service
- [ADR-058] Les jetons sont chiffrés avec un trousseau versionné
- [ADR-059] Le journal d'audit est partitionné par mois, purgé par `DROP`

### Documentation

- `Deployment.md`, `DevOps.md`, `Production.md`, `UserGuide.md`,
  `RoadmapV2.md`, `RoadmapV3.md` — six documents nouveaux.
- `API.md` §16–17, `Database.md` §16, `Architecture.md` §17, index d'ADR complété
  de 034 à 059.

### Ce qui n'a pas été fait, et qui était demandé

Énoncé plutôt qu'omis. Le détail est dans `Architecture.md` §17.5 et `TODO.md`.

- **IA temps réel pendant les réunions** : la table `meeting_session` existe et
  n'est remplie par rien.
- **Mode hors ligne** : seule la capture l'est, depuis la phase 1.
- **Versions Desktop et Web** : Flutter les cible ; aucun build n'a été produit.
- **Écrans Flutter d'entreprise** : l'API existe, le client ne l'appelle pas.
- **`sync_job` et `partition_job`** : documentés, non écrits. Tant que le second
  n'existe pas, la protection d'ADR-059 repose sur quelqu'un qui y pense.
- **Notifications intelligentes** : les types existent, aucune logique de
  regroupement.
- Aucun appel réel à un fournisseur d'intégration n'a jamais été passé, et aucune
  mesure de charge n'a été faite.

---

## [0.4.0] — 2026-08-03

**Phase 3 — La couche IA.** Le produit passe de « capturer, planifier, retrouver »
à « interroger ». Rien de l'existant n'a été cassé : les 481 tests des phases 1 et
2 passent inchangés, et le prompt d'extraction de la phase 1 conserve la même
empreinte pour que l'historique des `ai_run` reste valide.

### Ajouté — Domaine

- `chunking` : découpage déterministe sur frontières de phrases, hachage de
  contenu, estimation de budget. Aucune dépendance à un tokeniseur — cela
  épinglerait le projet au vocabulaire d'un fournisseur.
- `retrieval` : fusion par rangs réciproques (k = 60). Les scores lexicaux et
  vectoriels ne sont pas commensurables ; la fusion n'utilise que les positions.
- `intent` : routage déterministe des cinq questions imposées.
- `knowledge` : sept catégories d'entités, clés de résolution calculées en code.
- `memory` : contrat des faits durables, décroissance exponentielle de confiance.
- `EmbedderPort` et `ChatPort`, streaming en opération primaire.

### Ajouté — Prompts

- Dossier dédié `app/prompts/`, hors de `app.infra`, avec son propre contrat
  d'imports vérifié par `import-linter`.
- Sept prompts versionnés et empreintés : extraction de note, extraction
  d'entités, extraction de mémoire, réponse citée, trois résumés périodiques,
  narration des thèmes.
- Un test affirme que **tout** prompt manipulant du texte utilisateur déclare que
  ce texte est une donnée et non une instruction.

### Ajouté — Fournisseurs

- OpenAI, Claude, Gemini, Llama (auto-hébergé) et Mistral, derrière deux ports.
  Le choix est une variable d'environnement.
- Un test lit les sources et échoue si un module hors de la fabrique nomme un
  fournisseur.

### Ajouté — Schéma

- Migration 0006 : extension `vector`, tables `chunk`, `entity`,
  `entity_mention`, `conversation`, `conversation_message`, `memory`, `digest`.
- Index HNSW cosinus sur `chunk.embedding`, index partiel sur le retard
  d'encodage.
- RLS activée et forcée sur les sept tables dans la migration qui les crée.

### Ajouté — Services et workers

- Indexation (découpage synchrone, encodage asynchrone), récupération hybride,
  assistant conversationnel, extraction d'entités, mémoire, résumés périodiques.
- Trois jobs planifiés : `embed_job`, `extract_job`, `digest_job`.

### Ajouté — API

- `/v1/assistant/chat` et `/v1/assistant/chat/stream` (SSE), conversations,
  `/v1/search/semantic`, `/v1/search/index-status`, `/v1/entities`,
  `/v1/entities/themes`, `/v1/digests`, `/v1/memory`.

### Ajouté — Client

- Écran d'assistant avec réponse en flux et citations rendues sous chaque
  réponse générée.
- Écran de connaissances : entités, sujets récurrents, mémoire — inspectable et
  supprimable en un geste.
- Fil de résumés. Trois entrées ajoutées à la palette ⌘K.

### Modifié

- `app/infra/ai/prompts.py` devient un réexport de `app.prompts.extraction` :
  mêmes noms, même texte, même empreinte.
- `harden_schema` passe en API publique du domaine, désormais partagée par trois
  contrats de décodage contraint.
- La création et la modification d'une entrée réindexent ; la suppression
  logique retire ses chunks.
- Le contrat de configuration de production exige désormais un `embedding_backend`
  et un `chat_backend` réels. Le faux encodeur produit des vecteurs qui
  s'indexent et se retrouvent **avec succès** et n'encodent rien : la recherche
  sémantique aurait l'air de fonctionner en renvoyant les mauvaises notes.

### Corrigé

- **Privilèges du rôle de maintenance.** La migration 0003 avait posé des
  privilèges par défaut pour `mindflow_app` et `mindflow_readonly` mais pas pour
  `mindflow_maintenance` : toute table créée après elle — dont les cinq de la
  phase 2 — était invisible à la connexion inter-locataires. Sans erreur et sans
  symptôme jusqu'à ce qu'un job de fond en ait besoin.
- **Ordre des écritures à la réindexation.** SQLAlchemy émet les insertions
  avant les suppressions pour un même mapper ; un chunk remplaçant un autre au
  même index violait la contrainte d'unicité — le cas ordinaire d'une note
  modifiée.
- **Compteurs d'entités périmés.** Une entité retirée d'une réextraction
  conservait son compteur de la veille, faute d'être recomptée.
- **Routage des accents et apostrophes.** « que dois je faire aujourd hui »,
  produit couramment par la dictée, ne routait pas comme la forme accentuée.

### Décisions

- ADR-045 — Aucun fournisseur d'IA n'est couplé au projet : le port est le contrat
- ADR-046 — La largeur du vecteur est une décision de déploiement
- ADR-047 — Ce que la base sait exactement ne passe jamais par un modèle
- ADR-048 — Une question n'est pas une requête de recherche
- ADR-049 — La résolution d'entités est déterministe, l'extraction ne l'est pas
- ADR-050 — Le découpage est synchrone et gratuit, l'encodage asynchrone et payant
- ADR-051 — La mémoire ne retient que le durable, et l'oubli est définitif
- ADR-052 — Les résumés reçoivent leurs chiffres comme des faits établis
- ADR-053 — Les prompts sont des artefacts versionnés, dans un dossier dédié

### Documentation

- `AI.md` §13 — la couche IA telle qu'implémentée, **y compris les six écarts
  avec la conception de la phase 0** et ce que le système ne garantit pas.
- `Database.md` §15, `API.md` §15, `Architecture.md` §16.

### Tests

599 tests back-end (dont 179 nouveaux), 108 tests client, 5 contrats d'imports.

---

## [0.3.0] — 2026-08-03

**Phase 2 — Planification, recherche et mesure.** Le produit passe de « capturer
et consulter » à « capturer, planifier, retrouver et mesurer ». Aucune décision
des phases précédentes n'a été renversée ; deux défauts silencieux de la phase 1
ont été corrigés (ADR-041, ADR-042).

### Ajouté — Back-end

| Domaine | Contenu |
| --- | --- |
| Agenda | Vues jour / semaine / mois, bornes calculées dans le fuseau de l'utilisateur, retards dans leur propre section |
| Calendrier | Densité par jour agrégée en base, grille de semaines entières |
| Tâches avancées | Sous-tâches ordonnées, récurrence RRULE (sous-ensemble), report, replanification, épinglage, opérations groupées |
| Rappels | Décalages automatiques (`-1d@18:00`, `-15m`) re-dérivés à chaque changement d'échéance, rappels manuels jamais réécrits |
| Notifications | Centre en base écrit **avant** toute tentative de push, FCM (HTTP v1) et WNS, adaptateurs derrière un port |
| Recherche | Colonne générée `tsvector` + index GIN, grammaire `is:` `p:` `#tag` `@projet` `due:`, palette de commandes |
| Statistiques | Complétion, délai médian, séries, répartitions, et les chiffres qui dérangent |
| Historique | Table `activity_event` avec libellé dénormalisé, distincte de l'audit et des corrections IA |
| Bibliothèque | Tags avec fusion, projets avec compteurs, filtres enregistrés |

5 tables, 22 colonnes, 12 index et 1 conversion de type dans la migration 0005.
25 nouveaux points d'API. 311 tests passent ; `ruff`, `mypy --strict` (84
fichiers) et `lint-imports` (4/4) sont propres.

### Ajouté — Client Flutter

| Écran | Rôle |
| --- | --- |
| Agenda | Slivers par jour, en-têtes collants, retards en tête |
| Calendrier | Grille mensuelle, densité en points, anneau pour les retards |
| Palette de commandes | ⌘K : actions puis contenu, navigation au clavier |
| Recherche | Filtres rendus en chips, y compris ceux que le serveur a ignorés |
| Statistiques | Graphiques peints à la main, section « Ce qui ne va pas » |
| Historique | Timeline avec rail, verbes au passé |
| Notifications | Centre, marquage lu, badge dans la navigation |
| Bibliothèque | Projets, tags (fusion par renommage), filtres enregistrés |
| Détail d'une tâche | Sous-tâches, rappels, récurrence, priorité, report, historique |

Nouveau système de design (jetons, palette, thème clair/sombre conçus
séparément), coque adaptative (barre latérale ou barre basse). 90 tests passent,
`flutter analyze` est propre.

### Corrigé

Deux défauts de la phase 1, tous deux silencieux, tous deux trouvés en
implémentant la phase 2 :

- **Les travaux inter-tenants ne voyaient rien** (ADR-042). `privileged_session()`
  utilisait le rôle applicatif, `NOBYPASSRLS` par construction : le balayeur de
  captures et le répartiteur d'outbox traitaient zéro ligne depuis le premier
  jour, sans erreur ni log. Deux tests gardent désormais la propriété.
- **Les horodatages étaient naïfs** (ADR-041). 32 colonnes en `timestamp`
  comparées comme de l'heure locale : filtrage impossible contre un datetime
  aware, et regroupement par jour décalé du fuseau. Converties en `timestamptz`.

Et un défaut introduit puis corrigé pendant la phase : la seconde clé étrangère
de `task` vers `entry` rendait la relation ORM ambiguë et faisait échouer toute
la suite d'intégration jusqu'à ce que `foreign_keys` soit déclaré explicitement.

### Décisions

| ADR | Décision | Coût accepté principal |
| --- | --- | --- |
| ADR-037 | Recherche sur colonne générée `tsvector`, `websearch_to_tsquery` | Moins expressif qu'un `to_tsquery`, mais ne peut pas lever d'exception |
| ADR-038 | Le fournisseur de push est stocké par appareil, pas déduit | Une colonne de plus, et un client qui doit dire la vérité |
| ADR-039 | Une charge push est un pointeur, jamais une copie du contenu | Aperçu moins riche sur l'écran verrouillé |
| ADR-040 | Windows non empaqueté programme ses notifications localement | Un rappel local n'arrive que si l'application a tourné depuis |
| ADR-041 | Tous les horodatages en `timestamptz` | Une réécriture de table par colonne convertie |
| ADR-042 | Connexion dédiée pour les travaux inter-tenants | Une variable d'environnement et un rôle à provisionner |
| ADR-043 | Une sous-tâche n'est pas une entrée ; un seul niveau | On ne peut ni taguer ni rechercher une sous-tâche |
| ADR-044 | L'occurrence suivante part de l'échéance, pas de la complétion | Une tâche jamais terminée n'engendre rien |

### Compromis retenus

| Compromis | Gagné | Payé |
| --- | --- | --- |
| Agrégation en SQL plutôt qu'en Python | Le calendrier et les statistiques restent rapides à 50 000 entrées | Des requêtes plus difficiles à lire |
| Graphiques peints à la main | Aucune dépendance de plus, un seul passage de peinture | Deux types de graphiques, pas davantage |
| Palette de commandes plutôt qu'une navigation qui grandit | Ajouter un écran ne coûte pas un onglet | Une fonctionnalité invisible à qui n'essaie jamais ⌘K |
| Ordonnancement clairsemé (100, 200, 300) | Un déplacement réécrit une ligne | Une renumérotation quand l'espace manque |
| Réordonnancement par liste complète | Idempotent sur un lien instable | Une charge un peu plus grosse |
| Notification écrite avant le push | Rien n'est perdu si l'appareil est injoignable | Des notifications non lues qui s'accumulent |
| Deux chemins de notification Windows | Le poste de travail est réellement servi | Deux comportements à documenter et à tester |

### Améliorations proposées pour la phase 3

1. **Reprise automatique du mode dégradé** — toujours pas faite, et toujours la
   dette la plus coûteuse : les captures traitées quota atteint ne sont jamais
   reprises.
2. **Corpus d'évaluation annoté** (AI.md §7). La phase 2 mesure le taux de
   correction ; sans corpus, on ne sait toujours pas si une modification de
   prompt l'améliore.
3. **Pagination par curseur exposée au client** — la recherche et l'agenda
   chargent une page fixe.
4. **Synchronisation multi-appareils** (API.md §9), maintenant que plusieurs
   appareils sont réellement enregistrés.
5. **RAG** pour le rattachement aux projets, qui repose encore sur une
   correspondance floue de libellés.
6. **Tests de bout en bout du client** contre un back-end réel.
7. **Budget de coût par compte** — le coût est affiché, aucun plafond n'est
   appliqué.

### Non fait, sciemment

- **`docker compose up` n'a toujours pas été exécuté** : pas de démon Docker dans
  l'environnement de développement. Seule la CI valide ce chemin.
- **Aucun build Android, iOS ou Windows produit.** La CI les compile ; le chemin
  de notification Windows n'a donc jamais été exécuté sur un vrai poste.
- **Le graphe d'activité ne propose pas de zoom** ni d'export : hors périmètre.

---

## [0.2.0] — 2026-08-03

**Phase 1 — MVP fonctionnel.** Premier code applicatif. Le produit décrit en phase 0
tourne de bout en bout : on parle, la voix est transcrite, un modèle en extrait une
structure typée, et le résultat est stocké et consultable. Aucune décision de la
phase 0 n'a été renversée ; cinq ADR ont été ajoutés pour combler ce que la
conception n'avait pas prévu (ADR-029 à ADR-036).

### Ajouté — Back-end (FastAPI)

| Domaine | Contenu |
| --- | --- |
| Structure | Monolithe modulaire `api` → `services` → `domain`, avec `infra` et `workers` ; les 4 contrats d'`import-linter` échouent la CI si un module traverse une frontière |
| Base de données | 20 tables, migrations Alembic (schéma, RLS, rôles applicatifs, politique de recherche d'identité), montée **et descente** vérifiées en CI |
| Isolation | Row Level Security sur les 15 tables porteuses de `account_id`, `SET LOCAL app.account_id` par transaction, 23 tests d'isolation table par table |
| Authentification | Vérification locale des jetons Supabase (HS256 ou JWKS), provisionnement paresseux du compte |
| Capture | Déclaration idempotente, URL d'envoi signée, `complete` idempotent, transaction fermée avant la mise en file |
| Chaîne IA | Whisper → garde-fous anti-hallucination → LLM en sortie structurée stricte → résolution déterministe des dates → écriture |
| Ports | `TranscriberPort`, `AnalyzerPort`, `ObjectStoragePort`, `TaskQueuePort` — chaque moteur est remplaçable par configuration |
| API | REST versionnée, enveloppes `data`, erreurs RFC 9457 avec code applicatif stable, Swagger complet |
| Exploitation | Journalisation structurée avec identifiant de corrélation, métriques Prometheus, `/health` et `/ready` |
| Livraison | Dockerfile multi-étapes, `docker-compose.yml` (postgres, redis, migrations one-shot, api, worker), CI en 4 étages |

138 tests passent. `ruff`, `mypy --strict` (64 fichiers) et `lint-imports` (4/4) sont
propres. Couverture du domaine : 94 % pour un plancher de 85 %.

### Ajouté — Client (Flutter)

| Écran | Rôle |
| --- | --- |
| Connexion | Connexion et création de compte, un seul formulaire à deux modes |
| Tableau de bord | Compteurs, échéances proches, quota, file d'attente hors ligne |
| Liste des notes | Recherche et filtres exécutés côté serveur, complétion, suppression |
| Détail d'une note | Édition, échéance avec son expression d'origine, lien vers l'enregistrement |
| Enregistrement vocal | Micro, niveau d'entrée, envoi, suivi du traitement |
| Lecture audio | Audio d'origine, transcription, éléments extraits |

54 tests passent, `flutter analyze` est propre.

### Décisions

| ADR | Décision | Coût accepté principal |
| --- | --- | --- |
| ADR-029 | Supabase Auth vérifié localement, jamais d'appel réseau sur le chemin de requête | Deux schémas de signature à gérer (HS256 et JWKS) |
| ADR-030 | Sortie structurée stricte : un JSON non conforme est rejeté, jamais rattrapé | Une capture peut échouer à l'extraction ; sa transcription reste |
| ADR-031 | Balayeur de captures bloquées : la file est un cache, la base est la vérité | Une tâche périodique de plus |
| ADR-032 | Cible Python `>=3.11` au lieu de 3.13 | Quelques optimisations de version non utilisées |
| ADR-033 | Rôle applicatif `NOSUPERUSER`, `NOBYPASSRLS` obligatoire | Un rôle à provisionner dans chaque environnement |
| ADR-034 | File de captures persistée sur l'appareil avant tout appel réseau | Un fichier JSON réécrit en entier à chaque modification |
| ADR-035 | Fuseau IANA de l'appareil transmis à chaque capture | Une dépendance de plus, et un repli faillible hors d'Europe |
| ADR-036 | Mode d'authentification locale pour le développement, verrouillé par trois barrières | Un chemin d'authentification supplémentaire à maintenir |

### Corrigé

Défauts trouvés à l'implémentation et corrigés avant livraison. Chacun aurait été un
incident en production :

- **La RLS était inerte.** `FORCE ROW LEVEL SECURITY` ne s'applique pas aux
  superutilisateurs : l'application connectée en `postgres` contournait toutes les
  politiques. Rôle dédié + test qui vérifie `rolsuper is false` (ADR-033).
- **Interblocage sur verrou de ligne.** Les `BackgroundTasks` de FastAPI s'exécutent
  *avant* la fermeture des dépendances : la transaction de requête tenait encore la
  ligne que le worker tentait de mettre à jour. `complete_capture` gère désormais sa
  propre transaction et met en file strictement après le `commit`.
- **`create_app(settings)` était sans effet** : les dépendances lisaient le singleton
  global, donc les tests atteignaient un vrai Redis. Elles lisent `app.state.settings`.
- **Les garde-fous anti-hallucination étaient par moteur**, donc contournés par le
  moteur de test. Déplacés dans l'orchestrateur : « chaque moteur » (AI.md §3.2) veut
  dire chaque moteur.
- **Les boucles Whisper d'un seul mot passaient au travers** du détecteur de n-grammes
  (7 mots < 2 × fenêtre de 4). Ajout d'un contrôle de dominance d'unigramme.
- **`après-demain` était résolu comme `demain`** : le tiret n'était pas normalisé. La
  correction ne convertit les tirets qu'entre lettres, pour ne pas casser `12-06-2026`.
- **Valeurs par défaut ORM uniquement** : les insertions SQL brutes violaient des
  contraintes `NOT NULL`. `server_default` partout, et `compare_server_default` activé
  pour qu'Alembic détecte la dérive.
- **Le conftest avalait un échec de `downgrade`**, laissant la base de test sur un
  schéma périmé. Remplacé par une reconstruction complète, sans chemin silencieux.

### Compromis retenus

| Compromis | Gagné | Payé |
| --- | --- | --- |
| Monolithe modulaire plutôt que micro-services | Une seule transaction, un seul déploiement, un débogage simple | Une discipline d'imports à faire respecter par outillage, pas par bonne volonté |
| RLS en base plutôt que filtrage applicatif | L'isolation tient même si une requête oublie son `WHERE` | Un rôle non-superutilisateur obligatoire, et un `SET LOCAL` par transaction |
| Sortie structurée stricte plutôt que réparation de JSON | Aucune donnée inventée par une heuristique de rattrapage | Un taux d'échec d'extraction non nul, assumé et visible |
| Résolution des dates en code plutôt que par le modèle | Déterministe, testable, correcte au changement d'heure | Un module à maintenir, langue par langue |
| Sondage plutôt que SSE côté client | Aucune connexion longue à gérer sur mobile | Quelques requêtes de plus par capture |
| Fichier JSON plutôt que SQLite pour la file locale | Aucune dépendance embarquée | Réécriture intégrale à chaque modification |
| Quota qui dégrade au lieu de bloquer | Une pensée n'est jamais perdue pour une raison commerciale | Un plafond absolu à part, pour l'abus |

### Améliorations proposées pour la phase 2

Par ordre de valeur décroissante :

1. **Mesurer avant d'optimiser.** Le dispositif d'évaluation d'`AI.md` §7 n'existe
   qu'en conception. Sans corpus annoté, toute évolution du prompt est un pari. C'est
   le préalable à tout le reste.
2. **Reprise automatique du mode dégradé.** Les captures traitées en mode dégradé
   (quota atteint) ne sont aujourd'hui jamais reprises automatiquement. Un balayeur
   au retour du quota mensuel manque.
3. **RAG.** L'architecture est décrite (AI.md §6), rien n'est implémenté. La
   désambiguïsation des projets repose sur une correspondance floue de libellés, ce
   qui plafonnera vite.
4. **Synchronisation multi-appareils.** La file locale gère « ce qui n'est pas encore
   parti », pas « ce que l'autre appareil a modifié ». Le protocole d'API.md §9 reste
   à implémenter.
5. **Notifications d'échéance.** Une tâche extraite mais jamais rappelée ne vaut pas
   grand-chose. C'est la fonctionnalité la plus demandée par les personas du PRD.
6. **Tests de bout en bout du client** contre un back-end réel, avec `patrol` ou
   `integration_test`. Les tests actuels couvrent la logique, pas l'assemblage.
7. **Budget de coût par compte.** `PRICING_MICRO_EUR_PER_TOKEN` est renseigné mais
   aucun plafond n'est appliqué par compte.

### Non fait, sciemment

- **`docker compose up` n'a pas été exécuté** dans l'environnement de développement :
  aucun démon Docker n'y tourne. La composition est vérifiée par relecture et par la
  CI (étage `image`), pas par exécution locale.
- **Aucun build Android ou iOS n'a été produit.** Les dossiers de plateforme sont des
  artefacts d'outil, régénérés par `flutter create` ; la CI les génère et compile.

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
