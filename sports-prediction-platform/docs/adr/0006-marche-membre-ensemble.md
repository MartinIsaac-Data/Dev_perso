# ADR-0006 — Le marché est un membre de l'ensemble, pas une cible

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Les cotes dévigorisées sont l'estimateur public le plus performant. Les donner
massivement au modèle améliore spectaculairement le log-loss — et supprime
tout edge, puisque le modèle ne fait plus que recopier le marché.

## Décision

Le marché entre comme **quatrième membre explicite** de l'ensemble (M4), avec
un poids estimé sur l'historique mais **plafonné à 0.45**. Les modèles
statistiques et ML n'ont pas le droit d'importer `spp.market` : un contrat
`import-linter` l'interdit. La probabilité de marché n'apparaît qu'en argument
de fonction dans `spp.models.ensemble`, où le double comptage est visible.

## Conséquences

**Positives** — l'edge mesuré est interprétable. Le double comptage devient
un défaut de compilation plutôt qu'un biais silencieux.

**Négatives** — le log-loss affiché sera moins bon qu'avec un poids libre. Sur
l'exemple de référence, le blend absorbe 64 % de l'edge apparent (+3.61 % →
+1.30 % d'EV). C'est douloureux et c'est correct.

## Alternatives écartées

- *Poids libre* : converge vers un lisseur de cotes.
- *Ignorer le marché* : jette une information de très haute qualité et produit
  des edges nombreux et faux.
