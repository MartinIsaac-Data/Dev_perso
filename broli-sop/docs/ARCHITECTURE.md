# Architecture — Broli S&OP Portal

## Vue d'ensemble

```
 Excel (.xlsx) ──┐                          ┌─────────────── Broli.SOP.Web (Blazor Server) ───────────────┐
 ERP (Phase 3) ──┼─► Import (validation) ─► │ Pages · FilterBar · KPI · Chart.js · tableaux paginés         │
 SQL Server ─────┘          │               │ ApiClient typé (Bearer JWT) — ne connaît que Contracts        │
                            ▼               └───────────────────────────┬─────────────────────────────────┘
                  ┌──────────────────┐                                  │ REST / JSON
                  │ Base S&OP        │◄── Broli.SOP.Data (EF Core) ◄── Broli.SOP.API (contrôleurs, politiques)
                  │ (SQLite → SQL Srv)│        repositories                     │
                  └──────────────────┘                                  Broli.SOP.Application
                                                                  (AnalyticsEngine, calculs, services)
```

Le frontend n'accède jamais à Excel ni à la base : il appelle l'API. Changer la source de données revient à
réimplémenter `ISopReadRepository` / `IImportRepository` (ou à changer de fournisseur EF), sans toucher aux écrans.

## Couches

| Projet | Responsabilité | Dépend de |
|---|---|---|
| Domain | Entités et énumérations | — |
| Contracts | DTO, `SopFilter`, `TableQuery`, permissions, paramètres métier | — |
| Application | Règles métier, calculs, orchestration, ports (interfaces) | Domain, Contracts |
| Data | EF Core, requêtes d'agrégation, import transactionnel, DEMO | Application |
| Infrastructure | Sécurité, Excel, audit, horloge, notifications | Application |
| API | HTTP, authentification, autorisation, erreurs | Application, Data, Infrastructure |
| Web | Interface | Contracts |

## Modèle de données (schéma en étoile)

Dimensions : `DIM_PRODUCT` (CArtSAP, famille, marque, type matière, unité, poids, colisage, conversion TC, coût, stock de sécurité,
fournisseur principal, format, couleur), `DIM_CATEGORY`, `DIM_BRAND`, `DIM_SUPPLIER`, `DIM_COUNTRY` (temps de transit),
`DIM_AGENCY` (agences commerciales + usine interne), `DIM_WAREHOUSE`, `DIM_CUSTOMER`, `DIM_DATE` (clé yyyymmdd, calendrier fiscal).

Faits (clé de date entière `yyyymmdd`, sans FK dure vers `DIM_DATE` pour ne jamais bloquer un chargement) :

| Fait | Grain | Mesures |
|---|---|---|
| `FACT_SALES` | mois × produit × agence | Forecast (figé), Actual, Ordered. Pour matières / emballages : consommation usine (agence PLANT). |
| `FACT_INVENTORY` | date × produit × entrepôt | Stock (le dernier instantané du mois représente le mois) |
| `FACT_FORECAST` | mois × produit | Forecast à venir (dernière version) |
| `FACT_SUPPLY` | ligne de PO (PO × produit) | Qté, livré, TC, dates commande / requise / ETD / ETA / arrivée, statut, port, booking, BL, douane |
| `FACT_PRODUCTION` | mois × produit fini | Planifié, produit |

`FACT_TRANSIT` et `FACT_MRP` de la spécification sont couverts par les colonnes d'expédition de `FACT_SUPPLY` et par le calcul
à la volée (`TransitService`, `MrpService`) : une ligne de PO = une expédition. Un fractionnement d'une PO en plusieurs expéditions
nécessiterait une table `FACT_TRANSIT` dédiée (Phase 3, avec l'intégration ERP).

Opérationnel : `SOP_RISK` (registre), `SEC_USER`, `SEC_ROLE`, `SEC_USER_ROLE`, `SEC_ROLE_PERMISSION`, `SYS_AUDIT_LOG`,
`SYS_SETTING` (paramètres métier en JSON par section), `SYS_IMPORT_BATCH`. Toutes les lignes DEMO portent `IsDemo = 1`.

## Formules (toutes dans `Application/Calculations`, testées)

| Indicateur | Formule |
|---|---|
| Forecast Accuracy | `1 − Σ|A − F| / ΣA` au grain produit × mois (plancher 0 %) |
| BIAS | `(ΣF − ΣA) / ΣA` — positif = sur-prévision |
| Variance / Variance % | `A − F` / `(A − F) / F` |
| Statut forecast | `|Var %| ≤ tolérance` → On Track, sinon Under (A > F) / Over |
| Service Level | `Σ min(livré, commandé) / Σ commandé` |
| OTIF | lignes livrées dans la période, à l'heure (`arrivée ≤ date requise + tolérance`) **et** complètes (`livré ≥ x % commandé`) |
| Consommation moyenne | moyenne des N prochains mois de forecast, ou des N derniers mois réels, ou le max des deux (paramètre) |
| Stock disponible | stock physique (+ transit, + commandes ouvertes si paramétré) |
| Couverture | `disponible / consommation moyenne` ; *No Demand* si consommation nulle (jamais ∞) |
| Bandes | `< Critical` · `< Risk` · `< Watch` · Normal · `> Excess` (mois, paramétrables) |
| Stock de sécurité | valeur produit, sinon mois par famille, sinon mois par défaut × consommation moyenne |
| Excédent | `disponible − seuil Excess × consommation` (tout le stock si aucune demande) |
| Stock at Risk | produits en bande Critical ou Risk |
| Date de rupture | simulation jour par jour : stock − forecast du mois / nb jours + arrivées aux ETA |
| Risque ETA | ETA > rupture projetée (en ne comptant que les arrivées antérieures) → **Critical** ; ETA dépassée non reçue ou ETA > date requise → **Supply Risk** ; ETA dans la fenêtre de sécurité → **Watch** |
| TC | `quantité / qté par TC` du produit, sinon `kg / kg par TC` (paramètre) |
| Agrégats multi-produits | en TC (unités hétérogènes) ; dans l'unité de base si tous les produits filtrés la partagent |

### Phase 2

| Indicateur | Formule |
|---|---|
| Besoin net (MRP) | `max(0, Σ forecast(M+1…M+H) + stock de sécurité − (stock + commandes ouvertes + transit))` |
| Commande recommandée | besoin net arrondi au multiple de TC (si la consommation mensuelle ≥ ½ TC), sinon à l'unité |
| Délai d'approvisionnement | délai de production fournisseur + transit standard + délai port → entrepôt (import uniquement) |
| Date de besoin | date de rupture projetée (avec les approvisionnements déjà commandés) ; à défaut, fin d'horizon si le besoin vient du stock de sécurité |
| Date limite de commande | date de besoin − délai ; en retard si antérieure à aujourd'hui |
| Transit standard | fournisseur › pays (Configuration) › pays par défaut |
| Livraison estimée | (arrivée réelle ou ETA) + délai port → entrepôt si passage portuaire |
| Alerte « Stockout risk » | bande Risk, ou rupture projetée avant `aujourd'hui + max(délai, seuil Risk)` |
| Alerte « Slow moving » | stock > 0 et consommation des N derniers mois ≤ 5 % du stock |
| On-time fournisseur | livraisons à la date requise (+ tolérance) ÷ livraisons, sur les 12 derniers mois |
| Risque fournisseur | Critical si une PO ouverte arrive après la rupture ; High si % à l'heure < seuil d'alerte ou PO en retard ; Medium si < objectif OTIF |

Chaque résultat est un nombre fini ou `null` (affiché « — ») : pas de NaN ni d'Infinity possible.

## Périodes

Le filtre Année/Mois désigne la période. Sans mois : dernier mois disposant d'un stock. Le stock est pris au dernier mois
sélectionné (plafonné au dernier instantané disponible). Les comparaisons utilisent le bloc de mois précédent de même longueur.

## Cache et performance

`AnalyticsEngine` charge, pour un filtre, des agrégats par produit × mois, puis calcule toutes les positions, projections et
évaluations ETA une seule fois. Le résultat (snapshot) est mis en cache par *(version des données, jour, filtre)*.
`IDataVersion` est incrémenté à chaque import, mise à jour d'ETA, purge DEMO ou changement de paramètres.

## Sécurité

Authentification JWT (émis par `AuthService`, vérifié par l'API). Autorisation par **permission** (`executive.view`,
`finance.view`, `data.import`…) regroupées en rôles modifiables sans code. Le Web conserve le jeton dans le circuit Blazor
et dans le *session storage* chiffré ; il ne fait qu'afficher ce que l'API autorise.

## Données DEMO

`DemoDataGenerator` simule 13 mois jusqu'à aujourd'hui. Matières et emballages : simulation quotidienne avec politique de
réapprovisionnement, délais fournisseur + transit par pays, retards aléatoires ; finis : simulation mensuelle par la production.
Stock, réceptions, consommation et PO sont donc cohérents entre eux. Des profils (sain, tendu, critique, excédent, dormant)
garantissent la présence de chaque situation ; les films Rahma portent le scénario de démonstration (expédition arrivant après la rupture).
