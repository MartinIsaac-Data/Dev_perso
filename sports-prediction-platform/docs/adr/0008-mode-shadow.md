# ADR-0008 — Mode `shadow` prévu dès le jour 1

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Remplacer un modèle en production est risqué : un backtest favorable ne
garantit pas un comportement identique sur données réelles.

## Décision

Le champ `ml.prediction_runs.mode` distingue `live`, `replay`, `shadow` et
`backtest` dès le schéma initial. Un modèle candidat prédit en parallèle du
champion, sans être exposé, pendant au moins six semaines.

## Conséquences

**Positives** — la bascule se décide sur données réelles. L'écart
backtest/production devient mesurable, ce qui est le meilleur détecteur de
fuite résiduelle.

**Négatives** — coût de calcul doublé pendant la période de comparaison.
Négligeable à cette échelle.

## Alternatives écartées

- *Ajouter le mode plus tard* : impose de dupliquer toute la chaîne de
  prédiction, ou de polluer les tables existantes après coup.
