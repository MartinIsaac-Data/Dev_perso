# Déploiement — Windows Server / IIS / SQL Server

Ce guide s'adresse à l'équipe informatique. Une installation prend environ 30 minutes, une mise à jour 5 minutes.

## Vue d'ensemble

```
Navigateur ──HTTPS──► IIS : site « BroliSOP » (portail Blazor)
                                 │ http://127.0.0.1:5080  (même serveur, jamais exposé au réseau)
                                 ▼
                      IIS : site « BroliSOP-API » ──► SQL Server : base BroliSOP
```

- Deux pools d'applications : `BroliSOP-Web` et `BroliSOP-API`, avec l'identité par défaut *ApplicationPoolIdentity*.
- L'API n'écoute que sur `127.0.0.1` : seul le portail l'appelle. Le portail lui transmet l'adresse du navigateur
  (`X-Forwarded-For`), ce qui permet de limiter les tentatives de connexion par poste et non pour toute l'entreprise.
- Les réglages et secrets sont des variables d'environnement des pools, stockées dans `applicationHost.config` (hors des dossiers web).
  Aucun secret n'est présent dans les fichiers livrés.

## 1. Prérequis sur le serveur web

| Élément | Détail |
|---|---|
| Windows Server | 2019 ou 2022 |
| IIS | avec **WebSocket Protocol** (obligatoire) et **Application Initialization** (recommandé) |
| ASP.NET Core Hosting Bundle **10** | https://dotnet.microsoft.com/download/dotnet/10.0, puis `iisreset` |
| Certificat HTTPS | dans *Ordinateur local › Personnel*, pour le nom du portail (ex. `sop.broli.local`) |
| DNS | un enregistrement pointant `sop.broli.local` vers le serveur |

```powershell
Install-WindowsFeature Web-Server, Web-WebSockets, Web-AppInit -IncludeManagementTools
```

## 2. Base de données (DBA)

**Cas simple : SQL Server sur le même serveur que IIS, et l'installateur est administrateur de l'instance.**
Ajouter `-GrantDatabaseAccess` à la première installation (étape 4). Le script crée la base, puis donne l'accès à
l'identité du pool une fois celui-ci créé : ce compte n'existe qu'à partir de ce moment. Rien d'autre à faire ici.

**Sinon, le DBA prépare la base :**

1. Créer une base vide `BroliSOP` (SQL Server 2019 ou plus récent).
2. Donner l'accès au compte qui exécutera l'API. Par défaut, c'est l'authentification Windows, sans mot de passe stocké :
   - SQL Server **sur le même serveur** que IIS : `IIS APPPOOL\BroliSOP-API`. Ce compte n'existe qu'après la création
     du pool : utiliser plutôt `-GrantDatabaseAccess`, ou lancer l'installation une première fois, accorder les droits, puis la relancer ;
   - SQL Server **sur un autre serveur** : le compte machine du serveur web, `DOMAINE\NOMSERVEUR$`.

```sql
USE [master];
CREATE LOGIN [DOMAINE\NOMSERVEUR$] FROM WINDOWS;      -- ou [IIS APPPOOL\BroliSOP-API] si SQL Server est local
USE [BroliSOP];
CREATE USER [BroliSOP-API] FOR LOGIN [DOMAINE\NOMSERVEUR$];
-- Mode A (par défaut) : l'application crée et fait évoluer son schéma
ALTER ROLE db_owner ADD MEMBER [BroliSOP-API];
-- Mode B (-DbaAppliesMigrations) : le DBA applique le schéma, l'application ne fait que lire et écrire
-- ALTER ROLE db_datareader ADD MEMBER [BroliSOP-API];
-- ALTER ROLE db_datawriter ADD MEMBER [BroliSOP-API];
```

**Mode B** : avant l'installation, puis avant chaque mise à jour qui change le schéma, le DBA exécute `sql\migrations.sql`
fourni dans le paquet (SSMS ou `sqlcmd -i`). Ce script est idempotent : il peut être rejoué sans risque. Si le schéma
n'est pas à jour, l'API refuse de démarrer et indique les migrations manquantes.

Pour utiliser un compte SQL plutôt que Windows, passer `-SqlCredential (Get-Credential)` à l'installation.

## 3. Construire le paquet

Sur un poste de développement ou dans la CI (SDK .NET 10 et PowerShell 7) :

```powershell
pwsh broli-sop/deploy/build-release.ps1            # compile, teste, publie
# → broli-sop/release/broli-sop-<version>.zip
```

La CI GitHub produit aussi ce paquet à chaque PR (artefact `release-package`).

## 4. Première installation

Copier le zip sur le serveur web, le décompresser, puis ouvrir PowerShell **en administrateur** dans le dossier :

```powershell
Get-ChildItem . -Recurse | Unblock-File
.\Install-BroliSop.ps1 -SqlServer SQLPROD01 -HostName sop.broli.local -CertificateThumbprint <empreinte>
```

Le script effectue les opérations suivantes :
1. Il vérifie les prérequis. Rien n'est modifié si un prérequis manque.
2. Il demande deux fois le mot de passe du premier compte `admin`.
3. Il copie les fichiers dans `C:\inetpub\broli-sop` (paramètre `-InstallRoot`), crée les pools et les sites, et règle les droits.
4. Il enregistre la configuration : chaîne de connexion et clé de signature JWT, générée aléatoirement.
5. Il démarre l'application et attend que `http://127.0.0.1:5080/health` réponde. Au premier démarrage, l'API crée le
   schéma et les données de référence.
6. Il vérifie la connexion `admin`, puis **efface le mot de passe de la configuration**.

Ouvrir ensuite `https://sop.broli.local/`, se connecter en `admin`, créer les utilisateurs (*Administration › Users*),
puis importer les fichiers Excel (*Data Management*). Ordre : Supplier master → Product master → Inventory, Sales,
Forecast, Supply.

Paramètres utiles :

| Paramètre | Rôle |
|---|---|
| `-InstallRoot` | dossier d'installation (défaut `C:\inetpub\broli-sop`) |
| `-Database` | nom de la base (défaut `BroliSOP`) |
| `-SqlCredential` | compte SQL au lieu de l'authentification Windows |
| `-GrantDatabaseAccess` | crée la base si besoin et donne l'accès au compte de l'API, avec les droits du mode choisi (voir étape 2) |
| `-DbaAppliesMigrations` | mode B (voir étape 2) ; à combiner avec `-SchemaUpdatedByDba` une fois le script SQL exécuté |
| `-WebPort`, `-ApiPort` | ports (défauts 443 ou 80, et 5080) |
| `-InboxRoot` | dossier de dépôt Excel pour l'import automatique ; les droits de modification sont accordés à l'API |

Sans `-CertificateThumbprint`, le portail est servi en HTTP. À éviter en production : les mots de passe circulent à la connexion.

## 5. Mise à jour

```powershell
.\Install-BroliSop.ps1
```

Tous les réglages sont conservés. Le script arrête le portail (prévoir 1 à 2 minutes d'indisponibilité, hors heures de
réunion S&OP), déplace la version installée dans `backups\<date>`, installe la nouvelle version et vérifie qu'elle répond.
**Si l'API ne redémarre pas, l'ancienne version est remise en place automatiquement.** Les 3 dernières versions sont conservées.

Si la nouvelle version modifie le schéma de la base, le script s'arrête avant toute modification et demande :
- une **sauvegarde SQL Server** de la base, puis de relancer avec `-SqlBackupDone` ;
- en mode B, que le DBA exécute d'abord `sql\migrations.sql`, puis de relancer avec `-SchemaUpdatedByDba`.

## 6. Retour arrière

```powershell
.\Rollback-BroliSop.ps1                      # remet la version précédente
.\Rollback-BroliSop.ps1 -Backup C:\inetpub\broli-sop\backups\20261001-190455
```

La version retirée est conservée (`...-rolled-back`), si bien qu'un retour arrière peut lui-même être annulé.
La base n'est pas modifiée. Si la version retirée avait changé le schéma, restaurer la sauvegarde SQL prise avant la mise à jour.

## 7. Exploitation

| Sujet | Où / comment |
|---|---|
| État | `http://127.0.0.1:5080/health` sur le serveur (200 = OK) |
| Erreurs | Observateur d'événements › Journaux Windows › Application (sources *IIS AspNetCore Module V2* et *.NET Runtime*) |
| Sauvegardes | base `BroliSOP` : plan de maintenance SQL habituel (complète quotidienne + journaux) |
| Recyclage | les pools redémarrent chaque nuit à 03:00 ; le cache d'analyse est reconstruit au démarrage |
| Rafraîchissement automatique | planificateur intégré à l'API (*Data Management › Sources*) ; une seule instance de l'API doit tourner |
| Changer un réglage | Gestionnaire IIS › Pools d'applications › BroliSOP-API › Configuration Editor › `environmentVariables`, puis recycler le pool |
| Clé JWT | la changer déconnecte tous les utilisateurs ; elle est générée à la première installation |

Réglages disponibles (variables des pools, `__` sépare les niveaux) :

| Variable | Pool | Valeur |
|---|---|---|
| `ConnectionStrings__Sop` | API | chaîne de connexion SQL Server |
| `Database__Provider` | API | `SqlServer` |
| `Database__ApplyMigrations` | API | `true` (mode A) / `false` (mode B) |
| `Jwt__Key` | API | clé aléatoire d'au moins 32 caractères |
| `DataSources__InboxRoot` | API | dossier de dépôt Excel |
| `Smtp__Host`, `Smtp__Port`, `Smtp__From`, `Smtp__EnableSsl` | API | envoi des alertes par e-mail (optionnel) |
| `ForwardedHeaders__KnownProxies__0` | API | adresse du serveur du portail, seulement si le portail et l'API sont sur deux serveurs différents |
| `Api__BaseUrl` | Web | `http://127.0.0.1:5080/` |

## 8. Dépannage

| Symptôme | Cause probable |
|---|---|
| *HTTP Error 500.30 / 500.31* | Hosting Bundle absent ou installé avant IIS : le réinstaller, puis `iisreset` |
| L'installation échoue sur la santé de l'API | droits SQL (étape 2) ou serveur SQL injoignable : voir le journal Application |
| « The SQL Server schema is not up to date » | mode B : exécuter `sql\migrations.sql` de la version installée |
| Le portail s'affiche mais reste figé / « Reconnecting » | WebSocket Protocol non installé dans IIS |
| Tous les utilisateurs déconnectés après un redémarrage | profil utilisateur non chargé sur le pool Web (`Load User Profile = True`, réglé par le script) |
| « Too many attempts » pour tout le monde | le portail et l'API sont sur deux serveurs : déclarer le serveur du portail dans `ForwardedHeaders__KnownProxies__0` |

## Ce qui a été vérifié, et ce qui reste à valider

- **Vérifié automatiquement (CI, à chaque PR)** :
  - la construction du paquet ;
  - le schéma créé sur SQL Server 2022 par les migrations ;
  - toute la suite de tests exécutée sur SQL Server : imports, écritures, droits, refus de démarrer sur un schéma en retard ;
  - le script `migrations.sql` rejoué deux fois (idempotence), puis l'API démarrée sur ce schéma en mode B.
- **À valider sur le serveur cible**, car les scripts IIS ne peuvent pas s'exécuter hors Windows :
  - une première installation puis une mise à jour sur un serveur de recette ;
  - un retour arrière ;
  - le test de charge (`docs/LOAD-TEST.md`) refait sur l'infrastructure réelle.
