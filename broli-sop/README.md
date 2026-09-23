# Broli S&OP Portal

Application web S&OP pour Broli : un portail consultable depuis Chrome / Edge par ~50 utilisateurs
(DG, Supply, Sales, Finance, Production, Warehouse, Logistics), **sans Power BI**.
Source de données en Phase 1 : fichiers Excel importés ; Phase 2 : SQL Server / ERP — **sans refaire le frontend**.

> Stack : .NET 10 (LTS) · ASP.NET Core Web API · Blazor Web App (Interactive Server) · EF Core 10 (SQLite → SQL Server) ·
> Chart.js 4 (MIT, embarqué) · ClosedXML (Excel) · xUnit.

## État d'avancement — Phase 1 (MVP)

| Étape | Contenu | État |
|---|---|---|
| 1 | Architecture (8 projets, couches séparées) | ✅ |
| 2 | Modèle de données en étoile (9 dimensions, 5 faits + tables opérationnelles) | ✅ |
| 3 | Données DEMO (105 produits, 20 fournisseurs, 5 agences, 13 mois, ~800 PO, 14 risques) | ✅ |
| 4 | Backend / API REST (pagination, filtres et agrégations côté serveur, cache) | ✅ |
| 5 | Login + rôles + permissions (JWT, PBKDF2, verrouillage, audit) | ✅ |
| 6 | Executive Dashboard (10 KPI cliquables, tendances, top risques) | ✅ |
| 7 | Filtres dynamiques globaux (persistants, multi-sélection, reset, chips) | ✅ |
| 8 | Inventory + Forecast vs Actual + Coverage | ✅ |
| 9 | Supply / Open Orders (+ mise à jour ETA auditée) | ✅ |
| 10 | Risk Dashboard (moteur de détection + registre) | ✅ |
| + | Import Excel (validation / aperçu / erreurs), export Excel/CSV/impression, configuration, audit log, administration | ✅ |

## État d'avancement — Phase 2

| Étape | Écran | Question métier | État |
|---|---|---|---|
| 11 | **MRP** (`/mrp`) | Que faut-il commander ou produire, combien, et pour quand ? | ✅ |
| 12 | **Raw Materials** (`/raw-materials`) | Quelle matière première ou quel emballage nécessite une action ? | ✅ |
| 13 | **Films** (`/films`) | Quels films sont en rupture, en retard, en excédent ou à rotation lente ? | ✅ |
| 14 | **Finished Goods** (`/finished-goods`) | Peut-on servir la demande par famille, et la production suit-elle ? | ✅ |
| 15 | **Logistics & Transit** (`/transit`) | Où est chaque conteneur, et quand sera-t-il dans notre entrepôt ? | ✅ |
| 16 | **Supplier Performance** (`/suppliers`) | Quel fournisseur livre le plus souvent en retard ? | ✅ |

- **MRP** : stock, forecast M+1…M+4 (horizon paramétrable), commandes ouvertes, transit, stock projeté, couverture,
  besoin net = Σ forecast + stock de sécurité − (stock + commandes + transit), **commande recommandée arrondie au TC**,
  délai d'approvisionnement (production fournisseur + transit + port → entrepôt), date de besoin, **date limite de commande**
  et retard éventuel (« Order this week », « Late »).
- **Raw Materials / Films / Finished Goods** : un seul moteur, trois vues. Alertes automatiques par article :
  *Shortage* (couverture critique), *Stockout risk* (rupture avant qu'un réapprovisionnement lancé aujourd'hui puisse arriver),
  *Late supply* (PO en Supply Risk/Critical), *Excess*, *Slow moving* (consommation des N derniers mois < 5 % du stock).
  Conversion kg → TC paramétrable. Films : regroupement par marque, format, couleur ; familles « film » paramétrables.
  Finished Goods : stock, forecast, ventes, production, service level, couverture par famille (Spaghetti, Macaroni, Short Pasta, Mayonnaise).
- **Transit** : PO, fournisseur, matière, quantité, TC, pays, port, booking, BL, ETD, ETA, arrivée réelle, douane, dédouanement,
  **livraison estimée** (ETA + délai port → entrepôt), temps de transit réel vs **standard** (fournisseur › pays paramétré › pays par défaut), retard, risque.
- **Suppliers** : commandes, % à l'heure, retard moyen, livraisons partielles (indicateur qualité, faute de données qualité),
  commandes ouvertes, en transit, temps de transit moyen vs standard, risque.
- **Drill-down (§23)** : Dashboard → Raw Materials → fournisseur (ses expéditions) → produit → PO → expédition, vérifié dans le navigateur.
- Exports Excel/CSV de chaque tableau (lignes filtrées uniquement) ; nouveaux paramètres dans *Configuration*
  (délai port → entrepôt, seuil d'alerte fournisseur, familles « film », fenêtre de rotation lente).
- Correctif de sécurité : un export exige désormais aussi la permission de l'écran concerné (un profil Sales ne peut plus exporter la Supply).

Le module S&OP Actions (Phase 3) apparaît dans le menu avec un badge « P3 ».

**Vérifié :** la solution compile sans avertissement ; **85 tests** passent (unitaires sur KPI, couverture, projection, ETA, import,
MRP, alertes matières, délais, score fournisseur ; intégration de l'API réelle) ; le parcours prioritaire (§42) et la chaîne de
drill-down (§23) ont été joués dans un navigateur ; aucun tableau ne déborde à 1 440 px de large.

## Démarrage rapide

Prérequis : [.NET SDK 10](https://dotnet.microsoft.com/download) (Windows, Linux ou macOS). Rien d'autre — la base SQLite est créée automatiquement.

```powershell
cd broli-sop
$env:Bootstrap__AdminPassword = "ChoisissezUnMotDePasse2026"   # compte "admin"
$env:Demo__UserPassword       = "MotDePasseDemo2026"           # comptes DEMO (dg, supply, sales…)
./run.ps1            # ou ./run.sh sous Linux/macOS
```

Ou dans deux terminaux :

```bash
dotnet run --project src/Broli.SOP.API --launch-profile http   # http://localhost:5080
dotnet run --project src/Broli.SOP.Web --launch-profile http   # http://localhost:5090
```

Ouvrir **http://localhost:5090**. Au premier lancement en environnement *Development* :
- la base `src/Broli.SOP.API/broli-sop.db` est créée (schéma, pays, rôles, calendrier, paramètres) ;
- les **données DEMO** sont générées ;
- le compte `admin` et les comptes DEMO sont créés. **Si les mots de passe ne sont pas fournis, un mot de passe aléatoire
  est généré et affiché une seule fois dans la console de l'API.** Aucun identifiant n'est écrit dans le code.

| Compte DEMO | Rôle | Ce qu'il voit |
|---|---|---|
| `admin` | ADMIN | tout, dont import, configuration, utilisateurs, audit |
| `dg` | MANAGEMENT | Executive, Demand, Supply, Inventory, Risks, valeurs financières |
| `supply` | SUPPLY | + modification des ETA et du registre des risques |
| `sales` | SALES | pas de Supply, **pas de valeurs financières** |
| `finance` | FINANCE | valeurs de stock |
| `warehouse`, `logistics`, `production` | … | voir *Administration › Roles & permissions* |

Pour repartir de zéro : arrêter l'API et supprimer `src/Broli.SOP.API/broli-sop.db*`.

## Le parcours prioritaire (§42)

1. Ouvrir le lien → page de connexion → se connecter (`dg`).
2. Executive Dashboard : 10 KPI (Total Stock, Coverage, Stock at Risk, Open Orders, TC in Transit, TC at Port,
   Forecast Accuracy, Service Level, OTIF, Forecast vs Actual), chacun avec variation vs période précédente et statut.
3. Barre de filtres : **Month › Sep**, **Product Family › Films**, **Brand › Rahma** → tous les KPI se recalculent côté serveur
   (Total Stock 274 → 6,7 TC ; Stock at Risk 25 → 3 SKUs sur les données DEMO du 23/09/2026).
4. Clic sur **Stock at Risk** → liste des produits concernés (FILM RAHMA MACARONI 500G, SPAGHETTI 500G, VERMICELLI 200G).
5. Clic sur un produit → stock, couverture, **date de rupture projetée**, commandes ouvertes, **ETA**, et l'action :
   *« Expedite PO 45000232 (Anatolia Films Ltd) — ETA 25/10 is 17 d after projected stockout 08/10 »*.

Chaque étape répond en 0,2–0,4 s en local (voir *Performance*).

## Structure

```
broli-sop/
├── Broli.SOP.sln
├── run.ps1 / run.sh
├── docs/ARCHITECTURE.md            ← modèle de données, formules (Phase 1 et 2), décisions
├── src/
│   ├── Broli.SOP.Domain            Entités (dimensions, faits, opérationnel), enums. Aucune dépendance.
│   ├── Broli.SOP.Contracts         DTO de l'API, SopFilter, permissions, paramètres métier (partagés API ↔ Web)
│   ├── Broli.SOP.Application       Logique métier : calculs KPI, couverture, projection, moteur ETA, conseiller d'actions,
│   │                               détection des risques, services par écran, validation d'import, export
│   ├── Broli.SOP.Data              EF Core : SopDbContext (SQLite/SQL Server), repositories, initialisation, générateur DEMO
│   ├── Broli.SOP.Infrastructure    Hachage des mots de passe, JWT, lecture/écriture Excel (ClosedXML), audit, horloge, notifications
│   ├── Broli.SOP.API               ASP.NET Core Web API : contrôleurs, politiques de permissions, gestion d'erreurs, rate limiting
│   └── Broli.SOP.Web               Blazor : pages, composants (filtres, KPI, graphiques, tableaux), client API typé
└── tests/Broli.SOP.Tests           xUnit : calculs, import, API de bout en bout
```

Règle de dépendance : `Web → Contracts` uniquement (le frontend ne connaît que l'API REST, jamais Excel ni la base) ;
`API → Application + Data + Infrastructure` ; `Data/Infrastructure → Application → Domain + Contracts`.

## Configuration

Tous les paramètres techniques passent par `appsettings.json` ou des **variables d'environnement** (`Section__Clé`).

| Clé | Rôle | Défaut |
|---|---|---|
| `Database__Provider` | `Sqlite` ou `SqlServer` | `Sqlite` |
| `ConnectionStrings__Sop` | chaîne de connexion | `Data Source=broli-sop.db` |
| `Jwt__Key` | clé de signature (≥ 32 caractères). **Obligatoire hors Development.** | aléatoire en dev |
| `Jwt__LifetimeMinutes` | durée de session | 600 |
| `Bootstrap__AdminUsername` / `Bootstrap__AdminPassword` | premier administrateur (créé si aucun utilisateur réel) | `admin` / — |
| `Demo__Enabled` | générer les données DEMO sur une base vide | `true` en Development |
| `Demo__UserPassword` | mot de passe des comptes DEMO | aléatoire |
| `Api__BaseUrl` (Web) | adresse de l'API | `http://localhost:5080/` |

Les **paramètres métier** ne sont pas dans les fichiers : ils sont en base et modifiables dans *Configuration*
(seuils de couverture, base de consommation — forecast / historique / max —, nombre de mois, prise en compte du transit,
stock de sécurité par défaut et par famille, conversion kg/TC, fenêtre d'alerte ETA, tolérances OTIF, objectifs,
temps de transit par pays, devise, calendrier fiscal, départements). Chaque modification est auditée et recalcule tous les écrans.

### Passer à SQL Server

```bash
Database__Provider=SqlServer
ConnectionStrings__Sop="Server=SRV-SQL;Database=BroliSOP;Trusted_Connection=True;TrustServerCertificate=True"
```

Le schéma est créé au démarrage (`EnsureCreated`). Aucune modification du frontend ni de la logique métier.
Pour l'exploitation durable sur SQL Server, introduire les migrations EF Core (Phase 3, voir *Limites*).

## Import des données Excel

*Data Management* (permission `data.import`) : **choisir le type → déposer le .xlsx → validation & aperçu → importer.**

- Modèles téléchargeables : SUPPLIER MASTER, PRODUCT MASTER, FACT_SALES, INVENTORY, SUPPLY, FORECAST
  (en-têtes foncés = obligatoires ; alias FR/EN acceptés, ex. « Code article », « Prévision », « Agence »).
- Contrôles : colonnes manquantes, valeurs manquantes, doublons (même clé dans le fichier), dates invalides,
  valeurs négatives, nombres mal formés, CArtSAP inconnus, fournisseurs / pays inconnus, statuts inconnus, ETA < ETD,
  ligne *Delivered* sans date d'arrivée…
- **Une seule erreur bloque l'import complet** ; les avertissements (nouvelle agence, nouvel entrepôt, nouvelle famille) sont affichés.
- Import transactionnel (tout ou rien) et idempotent (upsert sur la clé métier : un fichier corrigé peut être réimporté).
- **Le premier import réel de SUPPLIER MASTER ou PRODUCT MASTER supprime toutes les données DEMO** dans la même transaction :
  les données fictives ne se mélangent jamais aux calculs réels. Les faits ne peuvent pas être importés tant que seuls
  des produits DEMO existent. Ordre conseillé : Supplier master → Product master → Inventory, Sales, Forecast, Supply.

## Tests

```bash
dotnet test
```

- `CalculationTests` — précision du forecast (WMAPE), BIAS, variance, statut On Track / Under / Over, service level,
  couverture et bandes configurables, stock de sécurité, excédent, conversion TC, projection de rupture, moteur de risque ETA.
- `PeriodAndAdvisorTests` — résolution des périodes, recommandations d'action.
- `ImportValidatorTests` — chaque règle de validation d'import.
- `Phase2Tests` — besoin net, arrondi TC, date limite de commande, alertes matières, délais standard, score fournisseur,
  et les 4 modules via l'API (cohérence des compteurs, périmètres, permissions, exports).
- `ApiTests` / `ImportApiTests` — l'API réelle sur une base SQLite temporaire : 401 / 403, verrouillage après 5 échecs,
  10 KPI finis (jamais NaN/Infinity), scénario Films + Rahma jusqu'à l'action « Expedite », masquage des valeurs pour Sales,
  pagination/tri serveur, recherche, export filtré, audit d'une modification d'ETA, validation de la configuration,
  flux d'import complet (blocage, purge DEMO, réimport corrigé).

## Sécurité

Mots de passe hachés PBKDF2 (ASP.NET Core Identity) · verrouillage 15 min après 5 échecs · limitation des tentatives de connexion
par IP · jetons JWT signés à durée limitée · permissions vérifiées **par l'API** sur chaque endpoint (le menu masqué n'est qu'un confort) ·
valeurs financières retirées des réponses sans `finance.view` · HTTPS + HSTS hors développement · en-têtes de sécurité ·
session du navigateur chiffrée (Data Protection) · audit log (utilisateur, date, action, module, objet, ancienne → nouvelle valeur)
pour connexions, imports, purge DEMO, ETA, risques, configuration, utilisateurs, rôles et exports.

Préparé pour Active Directory / Microsoft Entra ID : l'authentification est isolée derrière `AuthService`/`ITokenService`,
et l'autorisation repose sur des permissions indépendantes du fournisseur d'identité.

## Performance

- Aucune table n'est envoyée au navigateur : filtres, agrégations, tri et pagination sont faits côté serveur.
- Les faits sont agrégés en SQL (une ligne par produit × mois) avec index sur `(ProductId, DateKey)`.
- Le calcul complet d'un filtre (positions de stock, couverture, projection jour par jour, risques ETA) est mis en cache
  10 min et partagé par tous les utilisateurs ; il est invalidé à chaque import, modification ou changement de paramètre.
- Mesuré sur les données DEMO : 35–45 ms par calcul de snapshot (≈ 0,5 s pour la toute première requête après démarrage), 0,2–0,4 s par navigation.

## Déploiement (Windows Server / IIS)

1. `dotnet publish src/Broli.SOP.API -c Release -o publish/api` et idem pour `src/Broli.SOP.Web`.
2. Deux sites IIS (ASP.NET Core Hosting Bundle 10) ou un reverse proxy ; le Web doit pouvoir joindre l'API (`Api__BaseUrl`).
3. Variables d'environnement : `ASPNETCORE_ENVIRONMENT=Production`, `Jwt__Key`, `ConnectionStrings__Sop`, `Database__Provider`,
   `Bootstrap__AdminPassword` (premier démarrage).
4. Activer **WebSockets** sur IIS (Blazor Server). Certificat HTTPS sur le site Web.
5. Pour plusieurs instances de l'API : partager la clé Data Protection et remplacer `IDataVersion` en mémoire par un compteur partagé.

## Limites connues / prochaines étapes

- Export PDF : via « Print / PDF » du navigateur (feuille de style d'impression dédiée) — pas de génération PDF serveur.
- MRP : les produits finis n'ont pas de plan de production futur dans le modèle ; leur besoin net est un besoin de production.
- Qualité fournisseur : pas de données qualité en Phase 1–2 ; les livraisons partielles servent d'indicateur.
- Commandes ouvertes, transit et port reflètent l'état **actuel** (pas d'historique des statuts) ; la période filtrée
  s'applique au stock, à la demande, aux réceptions et à l'OTIF.
- La projection mensuelle peut masquer une rupture intra-mois ; la date de rupture affichée provient d'une simulation journalière.
- Schéma créé par `EnsureCreated` : introduire les migrations EF Core avant l'exploitation SQL Server.
- Notifications : interface `INotificationPublisher` en place (journalisation) ; e-mail / Teams en Phase 3.
- Le détecteur « Demand Increase » est sensible à la saisonnalité (seuil par défaut 30 %, ajustable dans *Configuration*).
- Les données DEMO sont générées relativement à la date du jour : les chiffres varient légèrement d'un jour à l'autre.
