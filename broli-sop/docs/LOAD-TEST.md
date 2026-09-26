# Test de charge — 50 utilisateurs

Objectif (§ exigences non fonctionnelles) : au moins 50 utilisateurs simultanés, sans erreur ni dégradation visible.

## Méthode

Outil : `tests/Broli.SOP.LoadTest` (console .NET, sans dépendance externe).

```bash
# 1. Créer le schéma : démarrer une fois l'API sur une base vide (Demo__Enabled=false), puis l'arrêter
# 2. Charger un volume réaliste directement dans la base SQLite
dotnet run --project tests/Broli.SOP.LoadTest -c Release -- seed /chemin/load.db 3000 48
# 3. Démarrer l'API en Release sur cette base (Demo__Enabled=false, Refresh__Enabled=false), puis
dotnet run --project tests/Broli.SOP.LoadTest -c Release -- run http://localhost:5081/ admin '<mot de passe>' 50 120 2000 rapport.md
```

- **Volume** : 3 000 SKU (1/3 produits finis), 12 familles, 8 marques, 60 fournisseurs, 5 agences + usine, 48 mois de ventes,
  stocks, production, approvisionnements et forecast (≈ 645 000 lignes de faits), 200 risques, 500 actions.
  Les données sont marquées d'un lot d'import « load-test » ; elles ne servent qu'au test, jamais à la démo ni à la production.
- **Scénario** : chaque utilisateur virtuel enchaîne, avec 2 s de réflexion entre deux écrans, le parcours prioritaire
  Tableau de bord → Stock (+ lignes à risque) → Fiche produit → un module parmi Demande / Supply / MRP / Matières /
  Transit + Fournisseurs / Risques / Réunion + Actions → Recherche → Notifications.
  Filtres aléatoires : 35 % aucun, 30 % une famille, 20 % famille + marque, 15 % un mois.
- **Environnement** : conteneur Linux 4 vCPU, SQLite, API seule (sans Blazor), .NET 10 Release.

## Résultats

| | Avant | Après |
|---|---:|---:|
| Requêtes (120 s) | 4 630 | 4 777 |
| Erreurs | 0 | 0 |
| p50 | 4 ms | 2 ms |
| p95 | 132 ms | 12 ms |
| p99 | 1 477 ms | 69 ms |
| Maximum | 2 637 ms | 96 ms |
| Calcul d'un snapshot (p50) | ≈ 1 200 ms | 3 ms |
| Chargements base de données | 1 par filtre (504) | 1 par année et version de données |
| Mémoire (pic RSS) | 872 Mo | 760 Mo |

« Après » = serveur déjà démarré, comme en exploitation. Juste après un redémarrage, les ~50 premières requêtes simultanées
prennent jusqu'à ~1 s (compilation JIT et montée en charge du pool de threads), puis tout repasse sous 100 ms.

### Détail avant

| Endpoint | Requests | Errors | p50 ms | p95 ms | p99 ms | Max ms |
|---|---:|---:|---:|---:|---:|---:|
| actions | 76 | 0 | 5 | 52 | 1090 | 1090 |
| demand | 85 | 0 | 34 | 108 | 297 | 297 |
| demand rows | 85 | 0 | 3 | 15 | 38 | 38 |
| executive | 598 | 0 | 10 | 1477 | 1759 | 2637 |
| inventory | 598 | 0 | 7 | 21 | 30 | 831 |
| inventory rows | 598 | 0 | 2 | 5 | 14 | 1090 |
| materials | 82 | 0 | 125 | 1392 | 2435 | 2435 |
| meeting | 76 | 0 | 505 | 1329 | 1955 | 1955 |
| mrp | 77 | 0 | 6 | 424 | 1392 | 1392 |
| mrp rows | 77 | 0 | 3 | 48 | 61 | 61 |
| notifications | 598 | 0 | 1 | 10 | 228 | 832 |
| product | 598 | 0 | 7 | 14 | 436 | 1755 |
| risks | 72 | 0 | 35 | 1472 | 2145 | 2145 |
| search | 598 | 0 | 9 | 36 | 890 | 1854 |
| suppliers | 94 | 0 | 4 | 37 | 87 | 87 |
| supply | 112 | 0 | 3 | 10 | 118 | 1745 |
| supply rows | 112 | 0 | 1 | 7 | 29 | 48 |
| transit | 94 | 0 | 6 | 113 | 1448 | 1448 |
| **All** | 4,630 | 0 | 4 | 132 | 1477 | 2637 |

### Détail après

| Endpoint | Requests | Errors | p50 ms | p95 ms | p99 ms | Max ms |
|---|---:|---:|---:|---:|---:|---:|
| actions | 80 | 0 | 5 | 7 | 16 | 16 |
| demand | 88 | 0 | 9 | 16 | 20 | 20 |
| demand rows | 88 | 0 | 1 | 4 | 4 | 4 |
| executive | 617 | 0 | 9 | 70 | 72 | 96 |
| inventory | 617 | 0 | 4 | 10 | 11 | 36 |
| inventory rows | 617 | 0 | 1 | 3 | 4 | 10 |
| materials | 84 | 0 | 2 | 8 | 14 | 14 |
| meeting | 80 | 0 | 29 | 45 | 62 | 62 |
| mrp | 77 | 0 | 5 | 7 | 14 | 14 |
| mrp rows | 77 | 0 | 3 | 4 | 5 | 5 |
| notifications | 617 | 0 | 1 | 2 | 4 | 20 |
| product | 617 | 0 | 3 | 6 | 8 | 55 |
| risks | 75 | 0 | 11 | 27 | 31 | 31 |
| search | 617 | 0 | 9 | 12 | 17 | 24 |
| suppliers | 99 | 0 | 2 | 8 | 18 | 18 |
| supply | 114 | 0 | 2 | 4 | 7 | 8 |
| supply rows | 114 | 0 | 1 | 2 | 3 | 3 |
| transit | 99 | 0 | 6 | 13 | 28 | 28 |
| **All** | 4,777 | 0 | 2 | 12 | 69 | 96 |

## Ce qui a été corrigé

1. **Une seule lecture de la base partagée par tous les filtres.** Avant, chaque combinaison de filtres (famille, marque, mois…)
   relançait 6 requêtes SQL (≈ 850 ms sur 3 000 SKU). Désormais `AnalyticsEngine` charge une fois, pour tous les produits,
   une fenêtre couvrant toute l'année de la période (janvier N-1 → décembre N + horizon de forecast), la garde en cache
   (poids ∝ nombre de lignes) et applique filtres, agences et bornes de période en mémoire. Une période hors de cette fenêtre
   charge exactement ce dont elle a besoin (test `BaseWindowTests`).
2. **Boucles quadratiques supprimées** dans Risques, Matières, Fiche produit et Demande : recherche par produit via des
   index (`ILookup`) construits une fois par snapshot.
3. **Mémoire du cache bornée par le volume** (`SizeLimit`, poids proportionnel aux lignes) au lieu du nombre d'entrées.
4. **Préchauffage** (`AnalyticsWarmup`) : le snapshot par défaut est construit au démarrage et après chaque changement de
   données (import, rafraîchissement, correction), pour que les premiers utilisateurs du matin n'attendent pas.
   Désactivable par `Analytics:WarmUp=false`.

Pour rejouer le test après une évolution, relancer les commandes ci-dessus et comparer au tableau « Après ».
