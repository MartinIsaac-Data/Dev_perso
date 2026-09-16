# ADR-0003 — Feature store unique partagé entraînement / production

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

La cause la plus fréquente d'écart entre un backtest brillant et une
production décevante est le *training/serving skew* : deux implémentations
d'une même feature, l'une en notebook, l'autre en production.

## Décision

Une seule implémentation par feature, déclarée dans un registre YAML
versionné, appelée par les deux chemins. La clé primaire de
`features.values` est `(match_id, competitor_id, as_of_ts,
feature_set_version)` : **une valeur de feature n'existe que relativement à
un instant de calcul**. Le vecteur est haché (`feature_hash`).

## Conséquences

**Positives** — skew impossible par construction. Le hash détecte les
révisions rétroactives. Une prédiction passée est rejouable à l'identique.

**Négatives** — plus rigide qu'un notebook : changer une formule impose
d'incrémenter une version et de recalculer. C'est le coût assumé.

## Alternatives écartées

- *Recalcul à la volée sans stockage* : empêche de prouver ce qui a servi.
- *Feature store tiers (Feast, Tecton)* : surdimensionné à cette échelle, et
  ajoute une dépendance lourde pour un besoin que 300 lignes couvrent.
