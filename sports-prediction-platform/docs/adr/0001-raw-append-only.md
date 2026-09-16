# ADR-0001 — Couche `raw` immuable et append-only

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Les fournisseurs de données sportives corrigent leur historique : un xG est
révisé à J+3, un carton réattribué, une composition publiée par erreur
retirée. La tentation naturelle est de parser directement vers des tables
relationnelles et de mettre à jour en place.

## Décision

Toute réponse d'un fournisseur est stockée telle quelle dans
`raw.observations` (JSONB + `fetched_at`), en **append-only**. Les droits
`UPDATE` et `DELETE` y sont révoqués. La canonisation lit `raw` et écrit
`core` ; elle ne modifie jamais `raw`.

## Conséquences

**Positives** — on peut répondre à « que voyait le modèle au moment où il a
prédit ? », donc backtester honnêtement. On peut re-parser rétroactivement
sans re-télécharger. Les erreurs de parsing sont réparables.

**Négatives** — volumétrie plus élevée (~60 Go de JSONB à 3 ans) et une
politique de rétention à gérer (90 jours en ligne, puis Parquet).

## Alternatives écartées

- *Parser directement en `core`* : perd définitivement l'état passé. C'est la
  cause n°1 de backtests faussement positifs dans ce domaine.
- *Conserver les fichiers bruts sur object storage seulement* : perd
  l'indexabilité, donc le diagnostic de qualité devient impraticable.
