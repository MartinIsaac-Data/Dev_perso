# ADR-0007 — Deux runs de prédiction par match

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Les compositions officielles sont publiées vers T−60 min et déplacent
significativement les probabilités. Un run unique oblige à choisir entre
prédire tôt (sans compos) ou tard (peu de temps pour agir).

## Décision

Deux runs archivés séparément : `pre-lineup` à T−24 h, et `post-lineup`
**déclenché par l'événement de publication des compositions**, pas par
l'horloge. Le second est celui qui porte la décision.

## Conséquences

**Positives** — la fenêtre T−60 → T−10 min est celle où le système a le plus
de valeur ajoutée (information publique, pas encore intégrée partout). On
mesure aussi l'apport réel des compositions en comparant les deux runs.

**Négatives** — double le volume de prédictions et impose un déclenchement
événementiel, donc une latence d'ingestion des compositions à surveiller.

## Alternatives écartées

- *Run unique à T−24 h* : ignore l'information la plus fraîche.
- *Run continu toutes les 15 min* : coût de calcul sans gain, les features ne
  changent pas entre deux publications.
