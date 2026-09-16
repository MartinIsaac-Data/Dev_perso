# 17 — Risques et plan de validation avant production

---

## 1. Risques techniques

| # | Risque | Prob. | Impact | Détection | Mitigation |
| --- | --- | --- | --- | --- | --- |
| T1 | **Matching d'entités défaillant** — cotes attribuées au mauvais match | Élevée | **Critique** | Overround reconstruit hors de [0.5 %, 25 %] ; contrôles de cohérence | Matching en 3 passes · file de revue manuelle · seuil de confiance élevé |
| T2 | **Historique de cotes indisponible ou trop cher** | Moyenne | **Bloquant** | À la première tentative d'achat | **À résoudre avant le jour 1** (doc 16) |
| T3 | Changement de format d'un fournisseur | Élevée | Moyen | Tests de contrat en CI | Deux sources sur les données bloquantes · quarantaine |
| T4 | Révision rétroactive de l'historique | **Certaine** | Élevé | Recalcul de `feature_hash` | Bitemporalité · alerte · marquage des backtests à rejouer |
| T5 | Volumétrie des cotes (240 M lignes/an) | Moyenne | Moyen | Métriques de taille et de latence | Partitionnement dès le jour 1 · archivage Parquet · TimescaleDB en option |
| T6 | Latence des compositions trop élevée | Moyenne | Élevé | Mesure du délai publication → ingestion | Fournisseur choisi sur ce critère · deux sources |
| T7 | Perte de base de données | Faible | **Catastrophique** | — | PITR managé · **test de restauration mensuel effectif** |
| T8 | Training/serving skew | Moyenne | Élevé | Test de régression sur 200 matchs | Feature store unique · même code en backtest et en production |
| T9 | Dérive silencieuse en production | Élevée | Élevé | PSI, ECE glissant | Alerte de calibration qui **suspend les signaux** |
| T10 | Dépendance à un fournisseur unique | Moyenne | Élevé | — | Couche d'abstraction par connecteur · deux sources |

> **T4 est marqué « certaine ».** Ce n'est pas un pessimisme de façade : tous
> les fournisseurs de données sportives révisent leur historique. La question
> n'est pas de l'éviter mais de le détecter, ce que seule la bitemporalité
> permet.

---

## 2. Risques statistiques — les plus graves

| # | Risque | Pourquoi c'est grave | Détection | Mitigation |
| --- | --- | --- | --- | --- |
| S1 | **Fuite de données** | Produit un backtest excellent et une production décevante, sans aucun symptôme intermédiaire | Suite de tests anti-fuite · comparaison backtest/production | 11 parades du doc 07 §2 · `make test-leakage` avant tout backtest |
| S2 | **Surapprentissage au backtest par itérations** | Se produit **sans erreur de code**. Le danger le plus insidieux du projet | Compteur d'essais · holdout scellé | Pré-enregistrement des hypothèses · budget d'essais · paper trading |
| S3 | **Modèle décalibré** | Produit des EV faux dans le sens de la sur-confiance : **plus de signaux, tous mauvais** | ECE glissant · courbe de fiabilité | Calibration mensuelle · alerte critique qui suspend les signaux |
| S4 | **Échantillon insuffisant** | 5 500 matchs et 45 features : la marge est mince | Ratio obs/features · intervalles de confiance | Budget de features strict · régularisation forte · contraintes de monotonie |
| S5 | **Non-stationnarité** | Les règles, les styles et les marchés changent. Un modèle entraîné sur 2019-2022 peut être obsolète | PSI · performance par saison | Fenêtre glissante · ré-entraînement trimestriel · pondération par récence |
| S6 | **Double comptage du marché** | Le modèle devient un lisseur de cotes : excellent log-loss, aucun edge | Corrélation entre membres · poids du stacking | Plafond de poids · `import-linter` interdit l'accès direct au marché |
| S7 | **Biais de sélection des matchs backtestés** | On ne teste que les matchs bien couverts, qui sont les plus efficients | Taux de couverture publié | Résultats stratifiés par liquidité |
| S8 | **Confondre chance et edge** | ROI positif avec CLV négatif : le pire scénario, parce qu'il est convaincant | CLV avec test de significativité | **Règle de gouvernance : CLV positif obligatoire** |
| S9 | **Comparaisons multiples** | 1 000 comparaisons/jour produisent des EV positifs par hasard | Nombre de tests · seuils ajustés par marché | Espace de recherche réduit aux marchés bien calibrés |
| S10 | **Sous-estimation de la corrélation entre paris** | Plusieurs paris sur un même match ou une même journée ne sont pas indépendants | Variance réalisée vs théorique | Plafonds d'exposition par match et par jour |

### Les trois qui tuent les projets

**S1, S2 et S8** sont responsables de la quasi-totalité des systèmes de
prédiction sportive qui « marchaient en backtest ». Ils partagent une
propriété : **ils ne produisent aucun symptôme visible.** Le backtest est
beau, le code est propre, les tests passent. C'est pour cela que le
protocole de validation ci-dessous existe et qu'il est non négociable.

---

## 3. Risques produit et externes

| Risque | Mitigation |
| --- | --- |
| **Fausse impression de certitude** donnée à l'utilisateur | Vocabulaire probabiliste · incertitude affichée systématiquement · pas de « pari sûr » · mention permanente |
| Utilisateur qui mise plus que de raison | Plafonds de mise recommandés · affichage du drawdown historique · rappel du risque |
| **Cadre légal et réglementaire** | Le projet est un outil d'analyse, pas un opérateur. Ne jamais placer de paris automatiquement. Vérifier le cadre applicable avant toute diffusion publique |
| Conditions d'utilisation des fournisseurs | Vérifier le droit de stockage et de réutilisation avant tout engagement |
| Limitation ou fermeture de comptes par les bookmakers | Hors du périmètre du système, mais à modéliser dans le backtest (doc 07 §5) |
| Attachement au projet empêchant de conclure à l'absence d'edge | **Critères de succès écrits avant les premiers résultats** (doc 13 §2) |

---

## 4. Plan de validation avant mise en production

Cinq portes successives. **Aucune ne peut être sautée, et l'échec d'une porte
renvoie à la phase précédente.**

### Porte 1 — Intégrité des données

| Contrôle | Seuil |
| --- | --- |
| Couverture des matchs sur les 5 ligues, 5 saisons | ≥ 98 % |
| Couverture des cotes (≥ 5 books) | ≥ 90 % |
| Couverture xG | ≥ 95 % |
| Couverture compositions officielles | ≥ 85 % |
| Contraintes `CHECK` violées | 0 |
| Conflits de sources non résolus | < 1 % des matchs |
| Test de restauration de sauvegarde | **Réussi** |

### Porte 2 — Absence de fuite

| Contrôle | Seuil |
| --- | --- |
| Suite de tests anti-fuite (11 fuites du doc 07) | **100 % verte** |
| Test de stabilité des `feature_hash` (recalcul à 6 mois) | Écarts expliqués à 100 % |
| Test de permutation (résultats mélangés) | ROI → 0 ± bruit |
| Test du modèle aléatoire | ROI ≈ −marge |
| Audit manuel de 20 prédictions rejouées | Aucune donnée postérieure utilisée |

> Le test de permutation est le plus révélateur : si mélanger les résultats
> ne détruit pas la performance, il y a une fuite quelque part.

### Porte 3 — Qualité probabiliste

| Contrôle | Seuil |
| --- | --- |
| **Brier Skill Score vs marché dévigorisé** | **> 0** sur le holdout |
| Log loss | < celui du marché |
| ECE | < 0.03 |
| Courbe de fiabilité | Écart < 3 pts sur tous les bacs ≥ 100 observations |
| Décomposition de Murphy | Fiabilité < 0.005 |
| Stabilité par saison | BSS > 0 sur ≥ 3 saisons sur 4 |
| Stabilité par ligue | BSS > 0 sur ≥ 4 ligues sur 5 |

**Si le BSS est négatif, le projet s'arrête ici** et retourne en phase
features/modèle. Un modèle moins bon que les cotes n'a aucune chance de
produire un edge, et tout ROI positif observé serait du bruit.

### Porte 4 — Robustesse du backtest

| Contrôle | Seuil |
| --- | --- |
| ROI en scénario **pessimiste** | > 0 avec IC bootstrap 95 % excluant 0 |
| Sensibilité à la méthode de de-vig | Le signe du ROI ne change pas |
| Sensibilité au seuil d'EV | Variation continue, pas de pic |
| Concentration du profit | Les 5 meilleurs paris < 40 % du profit total |
| Stratification par bac d'edge | Edge réalisé croissant avec l'edge annoncé |
| Drawdown maximal | < 30 % |
| Nombre d'essais de backtest | **Déclaré et pris en compte** dans l'interprétation |

### Porte 5 — Validation prospective (la seule qui compte vraiment)

| Contrôle | Seuil |
| --- | --- |
| Durée de paper trading | **≥ 3 mois** (6 recommandés) |
| Nombre de paris papier | **≥ 300** |
| **CLV moyen** | **> 0 avec t > 2** |
| % de paris à CLV positif | > 55 % |
| ECE mesuré en production | < 0.04 |
| Écart backtest / production sur le Brier | < 10 % relatif |
| Incidents de données non détectés | 0 |

> **Le critère décisif est le CLV, pas le ROI.** Sur 300 paris, le ROI a un
> intervalle de confiance d'environ ±10 points : il ne prouve rien. Le CLV,
> lui, converge assez vite pour trancher.
>
> L'écart backtest/production est le second critère le plus informatif : un
> modèle qui affiche un Brier de 0.19 en backtest et 0.22 en production a une
> fuite ou un skew, quelle que soit la beauté du reste.

---

## 5. Décision go / no-go

Après la porte 5, trois issues possibles, décidées sur les chiffres et non
sur l'attachement au produit :

| Issue | Condition | Action |
| --- | --- | --- |
| **GO** | Les 5 portes passées | Mise en production, mises réelles fractionnaires (Kelly ≤ 0.25), montée progressive, revue mensuelle |
| **GO partiel** | Portes 1-3 passées, porte 5 ambiguë (CLV positif mais t < 2) | Prolonger le paper trading de 3 mois. **Pas de mise réelle** |
| **NO-GO** | BSS ≤ 0 ou CLV ≤ 0 | **Retour en phase 4-6.** Le système reste utile comme outil d'analyse et d'affichage de probabilités, sans signaux de value |

Le troisième cas mérite d'être dit clairement : **un NO-GO n'est pas un
échec du projet.** Un système qui produit des probabilités calibrées, une
comparaison honnête au marché et une explication de chaque estimation a de la
valeur en tant qu'outil d'analyse — même s'il ne bat pas le marché. Ce qui
serait un échec, c'est de continuer à émettre des signaux de value après
avoir mesuré qu'ils n'en sont pas.

---

## 6. Surveillance continue après la mise en production

| Cadence | Contrôle | Action si dépassement |
| --- | --- | --- |
| **Horaire** | Fraîcheur des sources | Alerte, bascule sur source secondaire |
| **Quotidienne** | Couverture, conflits, échecs d'ingestion | Revue |
| **Hebdomadaire** | PSI des features surveillées | Investigation si > 0.25 |
| **Mensuelle** | ECE, Brier vs marché, CLV cumulé | Recalibration ; **suspension des signaux si ECE > 0.04** |
| **Mensuelle** | Test de restauration de sauvegarde | Correction immédiate |
| **Trimestrielle** | Ré-entraînement, comparaison en mode `shadow` | Bascule uniquement si BSS supérieur sur 6 semaines |
| **Annuelle** | Revue complète de l'architecture et des hypothèses | — |

---

## 7. Ce que ce système ne pourra jamais faire

À dire explicitement, dans la documentation et dans le produit :

1. **Prédire le résultat d'un match.** Il estime une distribution de
   probabilités, assortie d'une incertitude quantifiée.
2. **Garantir un profit.** Un edge positif mesuré sur le passé ne garantit
   pas le futur ; les marchés s'adaptent.
3. **Battre le marché sur tous les matchs.** Si un edge existe, il sera
   petit, rare, et concentré sur des niches (ligues peu couvertes, marchés
   secondaires, fenêtres temporelles précises).
4. **Remplacer le jugement.** Il rend le raisonnement explicite et
   mesurable ; il ne décide pas à la place de l'utilisateur.
5. **Voir ce que le marché voit.** L'information privée des clubs et le flux
   de paris lui resteront inaccessibles (doc 08 §5).

> La valeur de ce système ne réside pas dans sa capacité à trouver des paris
> gagnants. Elle réside dans sa capacité à **mesurer honnêtement s'il en
> trouve** — et à s'arrêter quand ce n'est pas le cas.
