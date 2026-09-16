# ADR-0005 — Statistiques en tables par sport, avec `extra JSONB`

**Statut** : acceptée · **Date** : 2026-09-16

## Contexte

Le football, le basketball et le tennis n'ont presque aucune statistique en
commun. Trois modèles de stockage étaient possibles : une table large à
colonnes nullables, un EAV générique, ou une table par sport.

## Décision

Une table par sport (`stats.football_team_match`, `stats.basketball_team_match`,
`stats.tennis_competitor_match`), typée fort, avec une colonne `extra JSONB`
pour la longue traîne des métriques exotiques.

## Conséquences

**Positives** — typage fort et surtout **contraintes d'intégrité possibles**
(`shots_on_target <= shots`, `fgm <= fga`). Ajouter un sport n'impacte aucune
table existante. Agrégats performants.

**Négatives** — les requêtes réellement multi-sports demandent une vue
d'union. Rare en pratique : les modèles sont par sport.

## Vérification

L'insertion de `shots=8, shots_on_target=12` est rejetée par la base. Sans
cette contrainte, cette ligne aurait produit une précision de tir de 150 % et
un modèle discrètement corrompu.

## Alternatives écartées

- *EAV* : rend toute contrainte d'intégrité impossible — rédhibitoire quand le
  risque principal du projet est la qualité des données.
- *Table large* : 80 % de colonnes nulles et un `ALTER TABLE` sur une table
  géante à chaque sport ajouté.
