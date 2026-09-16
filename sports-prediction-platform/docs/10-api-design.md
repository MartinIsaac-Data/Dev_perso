# 10 — API REST

> Contrat : `/api/v1`, JSON, horodatages ISO-8601 en UTC, pagination par
> curseur, erreurs RFC 7807 (`application/problem+json`).

---

## 1. Principes

| Principe | Application |
| --- | --- |
| **Toute réponse porte sa fraîcheur** | Chaque ressource expose `as_of` et `data_quality` |
| **Jamais de probabilité sans contexte** | Une probabilité est toujours accompagnée de son `model_version`, son `σ` et sa `reliability` |
| **Pagination par curseur** | L'offset dérive quand des données sont insérées en continu |
| **Filtres explicites** | Pas de `?q=` fourre-tout ; des paramètres typés |
| **Lecture seule en V1** | Aucun endpoint de mutation sauf le suivi de paris papier |
| **Versionnée dans l'URL** | `/api/v1` — une rupture de contrat sur les probabilités casserait tous les consommateurs |

---

## 2. Endpoints

### 2.1 Référentiel

```
GET  /api/v1/sports
GET  /api/v1/competitions?sport=football&country=FR&tier=1
GET  /api/v1/competitions/{id}
GET  /api/v1/seasons?competition_id=12
GET  /api/v1/venues/{id}
```

### 2.2 Équipes et joueurs

```
GET  /api/v1/teams?sport=football&competition_id=12&search=nantes
GET  /api/v1/teams/{id}
GET  /api/v1/teams/{id}/form?window=10&as_of=2026-09-16T12:00:00Z
GET  /api/v1/teams/{id}/ratings?scheme=elo&from=2025-08-01
GET  /api/v1/teams/{id}/matches?status=finished&limit=20
GET  /api/v1/teams/{id}/squad?as_of=2026-09-16
GET  /api/v1/teams/{id}/availability            # blessures, suspensions

GET  /api/v1/players/{id}
GET  /api/v1/players/{id}/stats?window=10
GET  /api/v1/players/{id}/impact                # PITS + incertitude
```

### 2.3 Matchs

```
GET  /api/v1/matches?date_from=2026-09-16&date_to=2026-09-20
                    &sport=football&competition_id=12
                    &has_value_signal=true
                    &min_data_quality=0.8
                    &cursor=...&limit=50

GET  /api/v1/matches/{id}                       # vue complète assemblée
GET  /api/v1/matches/{id}/stats                 # stats des deux équipes
GET  /api/v1/matches/{id}/h2h                   # H2H pondéré + poids
GET  /api/v1/matches/{id}/lineups               # probable + officielle
GET  /api/v1/matches/{id}/weather
GET  /api/v1/matches/{id}/referee
GET  /api/v1/matches/{id}/data-quality          # détail du score
```

### 2.4 Cotes et marchés

```
GET  /api/v1/matches/{id}/odds?market=1X2&bookmaker=pinnacle
GET  /api/v1/matches/{id}/odds/history?market=1X2&selection=H&from=...
GET  /api/v1/matches/{id}/markets               # tous marchés + probas + EV
GET  /api/v1/matches/{id}/market-probabilities?method=shin
GET  /api/v1/matches/{id}/movements?significant_only=true
GET  /api/v1/bookmakers
```

### 2.5 Prédictions et valorisation

```
GET  /api/v1/matches/{id}/predictions?market=1X2
GET  /api/v1/matches/{id}/predictions/history   # évolution des probas dans le temps
GET  /api/v1/matches/{id}/explanation?market=1X2&outcome=H
GET  /api/v1/value-signals?min_ev=0.03&sport=football&active=true
GET  /api/v1/value-signals/{id}
```

### 2.6 Modèles, backtests, monitoring

```
GET  /api/v1/models
GET  /api/v1/models/{id}
GET  /api/v1/models/{id}/calibration?window=90d
GET  /api/v1/models/{id}/performance?window=90d&breakdown=competition

GET  /api/v1/backtests
GET  /api/v1/backtests/{id}
GET  /api/v1/backtests/{id}/bets?cursor=...
GET  /api/v1/backtests/{id}/bankroll
GET  /api/v1/backtests/{id}/report            # HTML ou JSON

GET  /api/v1/health                            # liveness
GET  /api/v1/health/data                       # fraîcheur par source
GET  /api/v1/health/models                     # calibration, dérive
```

### 2.7 Suivi de paris (papier)

```
POST   /api/v1/bets                            # enregistrer un pari papier
GET    /api/v1/bets?status=open&cursor=...
PATCH  /api/v1/bets/{id}                       # dénouement manuel exceptionnel
GET    /api/v1/bets/summary?from=2026-01-01    # ROI, CLV, drawdown
```

---

## 3. Contrats de réponse

### 3.1 `GET /api/v1/matches/{id}`

```json
{
  "match": {
    "id": 884213,
    "sport": "football",
    "competition": { "id": 12, "code": "FR1", "name": "Ligue 1", "tier": 1 },
    "season": "2025/2026",
    "matchday": 7,
    "kickoff_utc": "2026-09-20T19:00:00Z",
    "venue": { "id": 44, "name": "Stade de la Beaujoire", "city": "Nantes",
               "altitude_m": 25, "surface": "grass", "is_neutral": false },
    "home": { "id": 101, "name": "FC Nantes", "short": "NAN" },
    "away": { "id": 118, "name": "Stade Rennais", "short": "REN" },
    "status": "scheduled"
  },
  "prediction": {
    "model_version": "football_1x2_ensemble@0.3.0",
    "as_of": "2026-09-20T18:05:00Z",
    "lineup_status": "confirmed",
    "markets": {
      "1X2": {
        "probabilities": { "H": 0.4824, "D": 0.2636, "A": 0.2540 },
        "sigma":         { "H": 0.0250, "D": 0.0170, "A": 0.0210 },
        "fair_odds":     { "H": 2.073,  "D": 3.793,  "A": 3.937 }
      },
      "OU": {
        "2.5": {
          "probabilities": { "OVER": 0.5069, "UNDER": 0.4931 },
          "fair_odds":     { "OVER": 1.973,  "UNDER": 2.028 }
        }
      }
    },
    "expected_goals": { "home": 1.62, "away": 1.08 },
    "expected_score": "1-1",
    "components": {
      "statistical": { "H": 0.4934, "D": 0.2591, "A": 0.2475 },
      "ml":          { "H": 0.4879, "D": 0.2595, "A": 0.2527 },
      "rating":      { "H": 0.5020, "D": 0.2550, "A": 0.2430 },
      "market":      { "H": 0.4617, "D": 0.2731, "A": 0.2652 }
    },
    "reliability": 0.72,
    "data_quality": 0.94
  },
  "market": {
    "as_of": "2026-09-20T18:04:12Z",
    "n_bookmakers": 11,
    "overround": 0.0397,
    "devig_method": "shin",
    "best_odds": { "H": { "odds": 2.10, "bookmaker": "bet365", "max_stake": 2500 } }
  },
  "value": [
    {
      "market": "1X2", "selection": "H",
      "model_prob": 0.4824, "market_prob": 0.4617,
      "fair_odds": 2.073, "market_odds": 2.10,
      "edge": 0.0207, "ev": 0.0130,
      "kelly_fraction": 0.0119, "recommended_stake_pct": 0.0030,
      "threshold_passed": false,
      "suppression_reason": "ev_below_uncertainty_adjusted_threshold"
    }
  ],
  "meta": { "generated_at": "2026-09-20T18:05:03Z", "cache_ttl_s": 60 }
}
```

> Noter `threshold_passed: false` **avec** le détail du calcul. L'API expose
> les signaux rejetés et la raison du rejet : c'est ce qui rend le système
> auditable, et ce qui évite que l'utilisateur croie que l'absence d'un
> signal est une absence de calcul.

### 3.2 `GET /api/v1/matches/{id}/explanation?market=1X2&outcome=H`

```json
{
  "outcome": "H",
  "final_probability": 0.4824,
  "baseline": 0.4310,
  "groups": [
    { "group": "Ratings d'équipe",    "delta_pp":  4.8, "weight": 0.41 },
    { "group": "Forme récente (xG)",  "delta_pp":  2.1, "weight": 0.18 },
    { "group": "Avantage domicile",   "delta_pp":  3.2, "weight": 0.22 },
    { "group": "Absences",            "delta_pp": -2.0, "weight": 0.11 },
    { "group": "Fatigue / calendrier","delta_pp": -0.9, "weight": 0.05 },
    { "group": "Signal de marché",    "delta_pp": -2.1, "weight": 0.35 },
    { "group": "H2H",                 "delta_pp":  0.0, "weight": 0.01 }
  ],
  "top_features": [
    { "feature": "elo_diff",            "value": 74.3,  "shap": 0.0312 },
    { "feature": "home_advantage_comp", "value": 0.27,  "shap": 0.0288 },
    { "feature": "xg_diff_weighted",    "value": 0.41,  "shap": 0.0175 },
    { "feature": "pits_missing_off",    "value": -0.09, "shap": -0.0198 },
    { "feature": "market_prob_devig",   "value": 0.4617,"shap": -0.0210 }
  ],
  "method": "TreeSHAP + décomposition additive de l'ensemble",
  "caveat": "Les contributions sont additives en log-odds puis converties en points de probabilité ; leur somme peut différer de l'écart total de ±0.3 pt."
}
```

---

## 4. Pagination, cache, erreurs

### Pagination par curseur

```json
{ "data": [...],
  "page": { "next_cursor": "eyJpZCI6ODg0MjEzfQ", "has_more": true, "limit": 50 } }
```

### Cache

| Ressource | TTL | Stratégie |
| --- | --- | --- |
| Référentiel (sports, compétitions) | 24 h | `Cache-Control: public` |
| Match à venir (> 24 h) | 10 min | Redis |
| Match imminent (< 3 h) | 30 s | Redis |
| Cotes | 30 s | Redis |
| Prédictions | 60 s, invalidé par événement | Redis + invalidation sur `lineup_published` |
| Backtests | 1 h | Redis |

`ETag` + `If-None-Match` sur toutes les ressources de lecture.

### Erreurs (RFC 7807)

```json
{
  "type": "https://api.example.com/problems/insufficient-data",
  "title": "Prédiction indisponible",
  "status": 422,
  "detail": "Aucune cote disponible pour ce match : la comparaison au marché est impossible.",
  "instance": "/api/v1/matches/884213/predictions",
  "data_quality": 0.31,
  "missing": ["odds", "lineups"]
}
```

| Code | Usage |
| --- | --- |
| 200 | OK |
| 304 | Non modifié (ETag) |
| 400 | Paramètre invalide |
| 404 | Ressource inexistante |
| **422** | **Ressource existe mais la prédiction n'est pas calculable** (données insuffisantes) |
| 429 | Rate limit |
| 503 | Dépendance indisponible (base, cache) |

> Le **422** est le code le plus important de cette API. Il matérialise la
> différence entre « pas de données » et « probabilité produite avec des
> données insuffisantes ». Retourner une probabilité dégradée sans le dire
> serait le défaut de conception le plus grave possible.

---

## 5. Sécurité et quotas

| Aspect | V1 | V2 |
| --- | --- | --- |
| Authentification | Clé API en en-tête | OAuth2 / JWT, comptes utilisateurs |
| Rate limiting | 60 req/min par clé | Par plan |
| CORS | Origine du dashboard uniquement | Configurable |
| Audit | Log des requêtes sur `/value-signals` | Complet |
| Mentions | Bandeau « estimations probabilistes, aucune garantie » retourné dans `meta` de chaque réponse de prédiction | idem |

---

## 6. Temps réel

Pour le dashboard, deux besoins distincts :

| Besoin | Solution | Pourquoi |
| --- | --- | --- |
| Rafraîchissement des cotes | **SSE** (`GET /api/v1/stream/odds?match_id=...`) | Unidirectionnel, simple, reconnexion native |
| Alertes | **SSE** (`/api/v1/stream/alerts`) | Idem |
| Interaction bidirectionnelle | Non nécessaire en V1 | WebSocket ajouté seulement si un besoin apparaît |

SSE plutôt que WebSocket : le flux est purement descendant, SSE passe les
proxies HTTP sans configuration et gère la reconnexion automatiquement.
WebSocket serait une complexité sans contrepartie.
