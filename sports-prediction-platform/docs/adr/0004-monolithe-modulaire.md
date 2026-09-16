# ADR-0004 — Monolithe modulaire, frontières appliquées en CI

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Le système comporte des responsabilités nettement séparées (ingestion,
features, modèles, marché, valorisation, API). Le réflexe serait d'en faire
autant de services.

## Décision

Un seul paquet Python `spp`, avec des frontières **vérifiées
mécaniquement** par `import-linter` en CI (quatre contrats). Le découpage en
services est reporté jusqu'à ce qu'un besoin réel l'impose.

## Conséquences

**Positives** — imports directs, typage traversant, refactoring mécanique,
coût d'exploitation minimal (~70 €/mois). Les frontières existent tout de
même, donc l'extraction future est un déplacement de dossier.

**Négatives** — pas de montée en charge indépendante par composant, et une
panne du processus affecte tout. Acceptable jusqu'à ~10 ligues × 3 sports.

## Vérification

Le contrat « les modèles ne lisent pas le marché » a été testé en introduisant
délibérément une violation : `lint-imports` sort en code 1. La frontière mord.

## Alternatives écartées

- *Microservices d'emblée* : ~10 semaines de plus, 200-500 €/mois, et un debug
  de prédiction qui devient une corrélation de traces.
- *Scripts et notebooks planifiés* : rend le point-in-time impossible à tenir.
