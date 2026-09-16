# ADR-0002 — Base bitemporelle

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Deux questions différentes doivent pouvoir recevoir deux réponses
différentes : « à quelle période ce fait était-il vrai ? » et « à partir de
quand le savions-nous ? ». Une base classique ne stocke que la première.

## Décision

Les tables de faits révisables portent quatre colonnes :
`valid_from`/`valid_to` (temps métier) et `recorded_at`/`superseded_at`
(temps de connaissance). Toute lecture point-in-time passe par une **fonction
unique** du repository, jamais par des clauses écrites à la main.

## Conséquences

**Positives** — l'anti-look-ahead devient structurel plutôt que
disciplinaire. Une révision rétroactive est détectable. La fonction unique est
testable, et elle l'est.

**Négatives** — les requêtes sont plus verbeuses (`DISTINCT ON` + double
filtre temporel) et les index plus nombreux. Le modèle mental est plus
exigeant pour un nouvel arrivant.

## Alternatives écartées

- *Versionner par `updated_at` seul* : ne distingue pas « la valeur a changé »
  de « on l'a apprise plus tard ».
- *Table d'audit séparée* : la reconstitution de l'état à une date devient une
  jointure coûteuse et facile à oublier.
