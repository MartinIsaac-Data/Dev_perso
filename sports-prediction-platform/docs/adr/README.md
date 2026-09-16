# Architecture Decision Records

Une ADR par décision structurante. Elles sont **numérotées et jamais
supprimées** : une décision annulée reçoit le statut `Remplacée par ADR-NNNN`,
parce que savoir pourquoi une décision a été abandonnée vaut autant que
connaître la décision courante.

| # | Décision | Statut |
| --- | --- | --- |
| [0001](0001-raw-append-only.md) | Couche `raw` immuable, append-only | Acceptée |
| [0002](0002-base-bitemporelle.md) | Base bitemporelle | Acceptée |
| [0003](0003-feature-store-unique.md) | Feature store unique partagé train/serve | Acceptée |
| [0004](0004-monolithe-modulaire.md) | Monolithe modulaire, frontières en CI | Acceptée |
| [0005](0005-stats-par-sport.md) | Statistiques en tables par sport + `extra JSONB` | Acceptée |
| [0006](0006-marche-membre-ensemble.md) | Le marché est un membre de l'ensemble, pas une cible | Acceptée |
| [0007](0007-deux-runs-de-prediction.md) | Deux runs de prédiction (pré/post composition) | Acceptée |
| [0008](0008-mode-shadow.md) | Mode `shadow` prévu dès le jour 1 | Acceptée |
| [0009](0009-nom-du-paquet-spp.md) | Le paquet Python s'appelle `spp`, pas `platform` | Acceptée |
