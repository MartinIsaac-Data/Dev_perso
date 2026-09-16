# ADR-0009 — Le paquet Python s'appelle `spp`, pas `platform`

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Le document de conception `docs/14-structure-du-projet.md` proposait un paquet
de premier niveau nommé `platform/`. Or **`platform` est un module de la
bibliothèque standard Python** (`platform.system()`, `platform.python_version()`).

Un paquet de premier niveau portant ce nom précède la bibliothèque standard
dans `sys.path` dès que la racine du projet y figure. Il masque alors le module
standard **pour tout le processus**, y compris pour les dépendances qui
l'importent — `structlog`, `pytest`, `setuptools` et de nombreuses
bibliothèques appellent `platform.*` au chargement. Le symptôme est un
`AttributeError` lointain dans une dépendance, sans rapport apparent avec le
code du projet.

## Décision

Le paquet s'appelle `spp` (sports prediction platform). Le document 14 a été
corrigé. La règle `ruff` `A` (*flake8-builtins*) est activée pour attraper les
masquages de noms dans le reste du code.

## Conséquences

**Positives** — aucun conflit, un préfixe court et sans ambiguïté, un
`import spp.core.settlement` lisible.

**Négatives** — un acronyme est moins explicite qu'un mot. Compensé par la
docstring du paquet, qui explique précisément ce choix.

## Alternatives écartées

- *Garder `platform` et compter sur les imports relatifs* : ne protège pas les
  dépendances tierces, qui font des imports absolus.
- *`sports_prediction_platform`* : correct mais verbeux à chaque import.
