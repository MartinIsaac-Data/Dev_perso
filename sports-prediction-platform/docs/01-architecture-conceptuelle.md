# 01 — Architecture conceptuelle

> Ce document fixe les frontières du système. Tout le reste en découle : si
> une frontière est mal placée ici, elle coûtera une réécriture plus tard.

---

## 1. Les six couches et leur contrat

Le système se lit de bas en haut. Chaque couche ne connaît que celle du
dessous, et expose un contrat stable.

| Couche | Responsabilité unique | Contrat exposé | Ne fait jamais |
| --- | --- | --- | --- |
| **L0 — Sources** | Fournir des octets | Réponse HTTP brute | — |
| **L1 — Ingestion** | Capturer sans interpréter | `raw.observations` (JSONB + `fetched_at`) | Transformer, nettoyer, dédupliquer |
| **L2 — Canonisation** | Réconcilier les sources en un modèle unique | `core.*` (matches, teams, stats…) bitemporel | Calculer des agrégats |
| **L3 — Features** | Calculer des variables point-in-time | `features.feature_values(entity, as_of_ts)` | Connaître le modèle qui les consomme |
| **L4 — Modèles** | Produire des distributions calibrées | `predictions` (proba + version modèle) | Décider d'un pari |
| **L5 — Décision & diffusion** | Comparer au marché, exposer, alerter | API REST, dashboard, `value_signals` | Recalculer une probabilité |

### Pourquoi cette séparation précise (le WHY)

**L1 séparée de L2** — La tentation est de parser directement en base
relationnelle. C'est l'erreur qui coûte le plus cher dans ce domaine. Les
fournisseurs de données sportives **corrigent leur historique** : un xG est
révisé trois jours après le match, un carton est réattribué, une composition
publiée par erreur est retirée. Si vous écrasez la donnée, vous perdez à
jamais la capacité de répondre à « qu'est-ce que le modèle voyait au moment
où il a prédit ? » — et votre backtest devient un mensonge. La couche raw
est **append-only et immuable**. C'est la seule assurance anti-look-ahead
qui soit structurelle plutôt que disciplinaire.

**L3 séparée de L4** — Un feature store partagé garantit que le calcul de
`form_xg_weighted_5` est identique en backtest et en production. La cause
n°1 d'écart entre backtest brillant et production décevante est le
*training/serving skew* : deux implémentations de la même feature. Une seule
implémentation, appelée par les deux chemins.

**L4 séparée de L5** — Le modèle ne doit pas savoir qu'il existe un marché,
sauf via le bloc « modèle marché » explicitement identifié dans l'ensemble.
Sinon on ne sait plus si la performance vient du modèle ou d'une
recopie déguisée des cotes.

---

## 2. Généricité multi-sport : où placer la couture

La question n'est pas « comment supporter N sports » mais « **qu'est-ce qui
est réellement commun** ». La réponse est plus large qu'on ne croit.

### 2.1 Ce qui est commun à tous les sports (noyau)

Le noyau modélise une abstraction : **une confrontation entre deux
compétiteurs, à une date, dans un contexte, avec un résultat ordonné**.

| Concept commun | Vrai pour football, basket, tennis, hockey, rugby, volley, MLB, NFL |
| --- | --- |
| `sport`, `competition`, `season`, `stage` | Oui |
| `competitor` (équipe **ou** joueur) | Oui — le tennis n'est qu'un sport où le compétiteur est une personne |
| `match` (2 compétiteurs, date, lieu, statut) | Oui |
| Avantage du terrain / service | Oui, avec des amplitudes très différentes |
| Rating de force (Elo/Glicko) | Oui, universel |
| Forme récente pondérée par récence | Oui |
| Fatigue / calendrier / voyage | Oui |
| Indisponibilités (blessure, suspension) | Oui (en tennis : forfait, blessure en cours de match) |
| Cotes, marchés, sélections, marge | Oui |
| Calibration, backtest, EV, bankroll | Oui |

**Décision** : ces concepts vivent dans `core.*` et `market.*`, sans aucune
colonne spécifique à un sport.

### 2.2 Ce qui est irréductiblement spécifique

| Dimension | Football | Basketball | Tennis |
| --- | --- | --- | --- |
| Structure du résultat | Buts (entiers, faibles, ~2.7) | Points (entiers, élevés, ~225) | Hiérarchie sets → jeux → points |
| Loi naturelle | Poisson / Poisson bivariée | Normale (différence de score) | Chaîne de Markov sur le point |
| Nul possible | Oui (~25 %) | Non (prolongation) | Non |
| Unité de temps | Minute (90 + arrêts) | Possession (pace) | Point servi |
| Granularité de l'effectif | 11 titulaires + 5 remplacements | 5 sur 8-10 en rotation | 1 |
| Variable de normalisation | Possession, PPDA | **Pace** (indispensable) | Points servis |
| Surface / terrain | Pelouse (mineur) | Aucune | **Surface (majeur)** |

**Décision** : le sport est un **plugin** qui fournit trois implémentations :

```python
class SportAdapter(Protocol):
    sport_code: str

    def outcome_space(self, market: str) -> list[str]:
        """Sélections possibles pour un marché donné."""

    def score_model(self) -> ScoreModel:
        """Loi génératrice du score : Poisson bivarié, normale, Markov."""

    def feature_specs(self) -> list[FeatureSpec]:
        """Features spécifiques au sport, en plus des features du noyau."""

    def settle(self, market: str, selection: str, result: Result) -> Settlement:
        """Règle de dénouement : gagné / perdu / remboursé / demi."""
```

Ajouter le hockey = écrire un adaptateur (Poisson + prolongation + tirs au
but) et une table `stats.hockey_team_match`. **Aucune migration du noyau.**

### 2.3 Les statistiques : verticales par sport, pas colonnes fourre-tout

Trois options ont été envisagées pour stocker les stats de match.

| | **Option A — colonnes larges** | **Option B — EAV** (`stat_name`, `value`) | **Option C — table par sport** |
| --- | --- | --- | --- |
| Principe | Une table `team_statistics` avec 200 colonnes nullables | Clé/valeur générique | `stats.football_team_match`, `stats.basketball_team_match`… |
| Lisibilité | Mauvaise (80 % de NULL) | Très mauvaise (aucune sémantique en base) | Excellente |
| Typage | Fort mais dilué | **Aucun** (tout en numeric/text) | Fort |
| Ajout d'un sport | Migration ALTER TABLE sur une table géante | Gratuit | Nouvelle table, zéro impact |
| Perf agrégats | Bonne | Mauvaise (pivots permanents) | Excellente |
| Requêtes croisées multi-sports | Faciles | Faciles | Nécessitent une vue d'union |
| Coût | Faible | Faible | Moyen |
| Complexité | Faible | Faible en écriture, **élevée en lecture** | Moyenne |
| Scalabilité | Mauvaise | Moyenne | Bonne |
| Pertinence MVP | Non | Non | **Oui** |

**Recommandation : Option C**, avec une échappatoire. Chaque table
spécifique porte une colonne `extra JSONB` pour les métriques exotiques ou
nouvelles d'un provider, avant qu'elles ne méritent une vraie colonne. On
gagne le typage fort sur les 40 métriques qui comptent et la souplesse sur la
longue traîne. L'EAV est rejeté parce qu'il rend impossible une contrainte du
type « `shots_on_target <= shots` », et ce genre de contrainte est votre
meilleure défense contre les données pourries.

---

## 3. Le flux de bout en bout, avec les instants qui comptent

```
 T-7j    Fixture publiée ──────────────▶ core.matches (status=scheduled)
 T-7j    Cotes d'ouverture ────────────▶ market.odds_snapshots (is_opening)
 T-5j    Stats des matchs précédents ──▶ stats.*_team_match
 T-72h   Point blessures ──────────────▶ core.availabilities
 T-48h   Bulletin météo ───────────────▶ core.weather_forecasts (h+48)
 T-24h   ┌─────────────────────────────────────────────────────┐
         │ RUN DE PRÉDICTION #1  « pre-lineup »                 │
         │  as_of_ts = T-24h → features → ensemble → prediction │
         └─────────────────────────────────────────────────────┘
 T-60m   Compositions officielles ─────▶ core.lineups (is_confirmed)
 T-55m   ┌─────────────────────────────────────────────────────┐
         │ RUN DE PRÉDICTION #2  « post-lineup »  ← le run qui  │
         │ compte pour la décision                              │
         └─────────────────────────────────────────────────────┘
 T-5m    Cotes de clôture ─────────────▶ market.odds_snapshots (is_closing)
 T+0     Coup d'envoi
 T+2h    Résultat ─────────────────────▶ core.match_results
 T+72h   Stats avancées révisées ──────▶ nouvelle version bitemporelle
         ┌─────────────────────────────────────────────────────┐
         │ ÉVALUATION : Brier, log loss, CLV, P/L               │
         └─────────────────────────────────────────────────────┘
```

**Point crucial** : chaque run de prédiction est archivé avec son `as_of_ts`,
sa `model_version_id` et le **hash du vecteur de features**. On peut donc
rejouer exactement une prédiction passée, et prouver qu'aucune information
postérieure n'y a contribué.

---

## 4. Trois architectures candidates pour le MVP

| | **Option A — Monolithe modulaire** | **Option B — Microservices** | **Option C — Notebooks + cron** |
| --- | --- | --- | --- |
| Forme | 1 repo, 1 process FastAPI + workers, modules à frontières strictes | 5-8 services (ingestion, features, ML, odds, API) | Scripts Python planifiés, sorties en CSV/Parquet |
| Temps jusqu'au 1er match prédit | ~4 semaines | ~10 semaines | ~1 semaine |
| Coût infra mensuel | 20-60 € | 200-500 € | ~0 € |
| Complexité opérationnelle | Faible | Élevée (réseau, traçage, versions de contrats) | Très faible |
| Debug d'une prédiction | Une stack trace | Corrélation de traces entre services | Impossible à rejouer |
| Scalabilité | Bonne jusqu'à ~10 ligues × 3 sports | Excellente | Nulle |
| Reproductibilité | Bonne | Bonne | **Mauvaise** (rédhibitoire) |
| Pertinence MVP | **Oui** | Non | Non |

**Recommandation : Option A.** Un monolithe modulaire avec des frontières de
module *appliquées par la structure des imports* (un module ne peut importer
que ses dépendances déclarées, vérifié en CI par `import-linter`). Le coût
d'un découpage en microservices se paie immédiatement et ne rapporte qu'à une
échelle qu'on n'atteindra pas avant deux ans. Mais les frontières sont
posées dès le jour 1 : le jour où l'ingestion de cotes doit tourner à part,
c'est un déplacement de dossier, pas une réécriture.

L'Option C est écartée non pas parce qu'elle est « peu professionnelle »,
mais parce qu'elle rend le principe #2 (point-in-time) impossible à tenir. Un
notebook qui lit `matches.csv` lit toujours la dernière version du fichier.

---

## 5. Découpage en modules et règles de dépendance

```
platform/
├── core/          domain : entités, value objects, règles de dénouement
│                  dépend de : rien
├── ingestion/     connecteurs providers, écriture raw
│                  dépend de : core
├── canonical/     réconciliation raw → core, résolution de conflits
│                  dépend de : core, ingestion (lecture seule)
├── features/      registre de features, calcul point-in-time
│                  dépend de : core
├── models/        statistique, ML, ratings, marché, ensemble, calibration
│                  dépend de : core, features
├── market/        parsing des cotes, de-vig, détection de mouvement
│                  dépend de : core
├── valuation/     EV, edge, staking, signaux
│                  dépend de : core, models, market
├── backtest/      moteur de simulation historique
│                  dépend de : core, features, models, market, valuation
├── api/           FastAPI, schémas Pydantic, auth
│                  dépend de : tout (couche la plus haute)
└── orchestration/ flows Prefect
                   dépend de : tout
```

Règle en CI : `core` n'importe rien du reste. `features` n'importe pas
`models` (sinon on crée un couplage qui empêche de recalculer les features
sans charger un modèle). `models` n'importe pas `market` — seul l'ensemble,
dans `models/ensemble.py`, reçoit la probabilité marché **en entrée**, ce qui
rend le double comptage visible dans la signature de fonction.

---

## 6. Modes d'exécution

Le même code doit tourner dans trois modes. C'est ce qui garantit l'absence
de skew.

| Mode | `as_of_ts` | Source des cotes | Usage |
| --- | --- | --- | --- |
| `live` | `now()` | Dernier snapshot | Production |
| `replay` | horodatage passé fourni | Snapshot ≤ `as_of_ts` | Backtest, debug d'une prédiction |
| `shadow` | `now()` | Dernier snapshot | Nouvelle version de modèle qui prédit sans être exposée |

Le mode `shadow` est ce qui permet de déployer un modèle v2 et de le comparer
au v1 sur données réelles pendant 6 semaines avant de basculer. Il est prévu
dès la conception parce que le rajouter après coup impose de dupliquer toute
la chaîne de prédiction.

---

## 7. Ce qui est délibérément hors périmètre

| Hors périmètre | Pourquoi |
| --- | --- |
| Placement automatique de paris | Risque réglementaire, risque de bug catastrophique, et surtout : tant que le CLV n'est pas prouvé positif sur 1000+ paris, l'automatisation ne fait qu'accélérer les pertes |
| Live betting / in-play | Contraintes de latence (< 2 s) et modèles de survie complètement différents. C'est un second produit, pas une feature |
| Scraping de sites protégés | Fragilité juridique et technique ; on paie des API |
| Multi-tenant / comptes utilisateurs | V1 mono-utilisateur. L'auth arrive en V2 |
| Modèles de joueurs individuels (player props) | Nécessite des données de tracking rarement accessibles à budget raisonnable ; V3 |

---

## 8. Résumé des décisions d'architecture

| ID | Décision | Justification courte |
| --- | --- | --- |
| ADR-01 | Couche raw immuable append-only | Seule défense structurelle contre le look-ahead |
| ADR-02 | Base bitemporelle (`valid_from`, `recorded_at`) | Les providers corrigent l'historique |
| ADR-03 | Feature store unique partagé train/serve | Élimine le training/serving skew |
| ADR-04 | Monolithe modulaire, frontières en CI | Coût/valeur au stade MVP |
| ADR-05 | Stats en tables par sport + `extra JSONB` | Typage fort + contraintes d'intégrité |
| ADR-06 | Le marché est un membre de l'ensemble, pas une cible | Évite le compresseur de cotes |
| ADR-07 | Deux runs de prédiction (pre/post lineup) | Les compos déplacent significativement les probabilités |
| ADR-08 | Mode `shadow` prévu dès le jour 1 | Impossible à rétrofitter proprement |
