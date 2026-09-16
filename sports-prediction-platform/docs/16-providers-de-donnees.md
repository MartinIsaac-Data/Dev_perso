# 16 — Fournisseurs de données

> **Avertissement** : les offres, tarifs et périmètres de couverture des
> fournisseurs changent souvent. Ce document classe les **catégories** et les
> **critères de choix** ; les prix et couvertures exacts doivent être
> vérifiés directement auprès de chaque fournisseur au moment de l'achat.
> Les fourchettes budgétaires ci-dessous sont des ordres de grandeur destinés
> à cadrer l'arbitrage, pas des devis.

---

## 1. Les cinq catégories de données, par criticité

| Catégorie | Criticité | Substituable ? | Coût relatif |
| --- | --- | --- | --- |
| **Historique de cotes** | **Bloquante** | Non | ★★★★☆ |
| Cotes temps réel | **Bloquante** | Partiellement | ★★★★★ |
| Résultats et calendriers | Bloquante | Oui (nombreuses sources) | ★☆☆☆☆ |
| Statistiques avancées (xG, événements) | Haute | Difficilement | ★★★★☆ |
| Compositions et blessures | Haute | Partiellement | ★★☆☆☆ |
| Météo | Faible | Oui | ☆☆☆☆☆ |

### Le point qui décide de tout

**L'historique de cotes est le seul actif non reconstituable.** On peut
toujours retrouver les résultats de la saison 2021-22 ; on ne peut pas
retrouver la cote affichée par Bet365 le 14 mars 2022 à 19h37 si personne ne
l'a enregistrée.

Conséquence opérationnelle : **acheter ou constituer l'historique de cotes
est la première dépense du projet, avant toute ligne de code de modélisation.**
Un projet qui développe six mois puis découvre qu'il ne peut pas backtester
a perdu six mois.

Et en corollaire : **démarrer la collecte de cotes en temps réel dès
aujourd'hui**, même sans modèle. Chaque jour sans collecte est un jour
d'historique définitivement perdu.

---

## 2. Cotes

### 2.1 Types de fournisseurs

| Type | Ce qu'ils offrent | Limites |
| --- | --- | --- |
| **Agrégateurs commerciaux d'odds** (ex. The Odds API, OddsJam, BetsAPI, Odds API providers divers) | API temps réel multi-books, parfois historique | Le nombre de books, la fréquence de rafraîchissement et la profondeur historique varient énormément selon le plan |
| **Fournisseurs de données sportives généralistes** (ex. Sportmonks, API-Football, SportRadar, Stats Perform) | Calendriers, résultats, stats et parfois cotes | Les cotes y sont souvent un produit secondaire, moins fréquemment rafraîchi |
| **Archives historiques ouvertes** (ex. football-data.co.uk) | Cotes de clôture historiques gratuites sur les grandes ligues européennes | **Cotes de clôture seulement**, pas d'évolution intra-journée ; couverture limitée aux ligues majeures |
| **API d'exchange** (ex. Betfair) | Cotes, volumes échangés, historique de marché | Excellent signal de liquidité ; complexité d'intégration plus élevée |
| **Collecte propre** | Contrôle total, coût marginal nul | Fragilité technique, conditions d'utilisation à vérifier au cas par cas |

### 2.2 Critères de sélection — dans l'ordre d'importance

1. **Profondeur historique** avec horodatage (pas seulement la clôture).
2. **Présence d'au moins un bookmaker « sharp »** — sans référence de
   qualité, le consensus est mou et le CLV n'est pas mesurable correctement.
3. **Fréquence de rafraîchissement** autorisée par le plan (le calendrier du
   doc 08 §1.4 demande 1 requête/minute en fin de fenêtre).
4. **Identifiants d'entités stables** — c'est ce qui rend le matching fiable
   (doc 08 §6).
5. **Couverture des marchés** au-delà du 1X2 (Over/Under, handicaps).
6. Quotas et coût au-delà.

### 2.3 Stratégie recommandée

```
V1  : 1 archive historique gratuite (cotes de clôture, 5 grandes ligues)
      + 1 agrégateur payant pour le temps réel et la construction
        d'historique intra-journée à partir d'aujourd'hui

V2  : ajout d'une source exchange pour la liquidité et le CLV
```

Le mélange est volontaire : l'archive gratuite permet de **démarrer les
backtests immédiatement** (même avec les seules cotes de clôture, ce qui
suffit à mesurer le Brier Skill Score contre le marché), pendant que la
collecte temps réel construit l'historique fin nécessaire aux backtests
réalistes de l'année suivante.

> **Attention méthodologique** : backtester contre des cotes de **clôture**
> donne des résultats systématiquement pessimistes (la clôture est le
> meilleur estimateur, donc la plus dure à battre). C'est une propriété
> utile : un modèle qui bat la clôture est solide. Mais il ne faut pas
> confondre ce résultat avec ce qu'on obtiendrait en pariant à J-2.

---

## 3. Statistiques et événements

| Type | Exemples | Ce qu'on y trouve | Ordre de grandeur |
| --- | --- | --- | --- |
| **Sources ouvertes / communautaires** | FBref (StatsBomb), Understat, Football-Data | xG, tirs, statistiques d'équipe, parfois événements | Gratuit à faible coût ; conditions d'utilisation et stabilité à vérifier |
| **API commerciales grand public** | API-Football, Sportmonks, Football-Data.org | Calendriers, résultats, compos, statistiques, blessures | Dizaines à quelques centaines d'€/mois selon le plan |
| **Fournisseurs professionnels** | Opta/Stats Perform, SportRadar, StatsBomb | Données événementielles complètes, xG propriétaire, tracking | Plusieurs milliers d'€/mois — hors de portée d'un MVP |

### Le compromis xG

Le xG est la feature la plus utile du football (doc 02 §C.1) et l'une des
plus chères. Trois options :

| | **A — xG d'un fournisseur** | **B — xG maison à partir des tirs** | **C — Sans xG** |
| --- | --- | --- | --- |
| Qualité | Bonne à excellente | Correcte si l'on a x/y, pied/tête, type d'action | Dégradée |
| Coût | Élevé | Coût du flux d'événements (moyen) | Faible |
| Cohérence historique | **Risque de révision de définition** | **Contrôlée par nous** | N/A |
| Contrôle | Aucun | **Total** | — |
| Pertinence MVP | Oui si budget | **Oui si le flux d'événements est accessible** | Repli acceptable |

**Recommandation** : option A en V1 pour aller vite, avec l'option B
préparée. L'argument décisif en faveur de B à terme est la **cohérence
historique** : un fournisseur qui change son modèle xG réécrit votre passé,
ce qui déclenche exactement l'alerte de révision rétroactive du doc 07 — et
oblige à ré-entraîner. Un xG maison, même légèrement moins bon, est stable,
et la stabilité vaut plus que la précision marginale dans ce contexte.

---

## 4. Compositions, blessures, absences

C'est la catégorie où **la latence compte plus que l'exhaustivité**.

| Besoin | Exigence |
| --- | --- |
| Compositions officielles | Disponibles **dans les 2 minutes** suivant la publication (T−60 min) |
| Compositions probables | Utiles, mais à traiter comme probabilistes |
| Blessures | Mise à jour ≥ 2×/jour, avec date de mise à jour exposée |
| Suspensions | Calculables soi-même à partir des cartons — **le faire** plutôt que d'en dépendre |

> Les suspensions sont déterministes (règles de cumul de cartons par
> compétition). Les calculer en interne supprime une dépendance et améliore
> la fiabilité. C'est un des rares endroits où « faire soi-même » est
> clairement supérieur.

**Un point souvent sous-estimé** : la valeur ajoutée du système est
maximale dans la fenêtre T−60 min → T−10 min, quand les compositions sont
publiques mais pas encore intégrées dans tous les marchés. Un fournisseur de
compositions lent annule cet avantage. **La latence des compositions est un
critère de sélection plus important que le prix.**

---

## 5. Météo

| Fournisseur | Note |
| --- | --- |
| **Open-Meteo** | Gratuit, sans clé, historique de prévisions disponible — le meilleur rapport qualité/contrainte pour cet usage |
| OpenWeatherMap | Offre gratuite limitée, historique payant |
| Visual Crossing | Bon historique, payant |

**Critère spécifique et non négociable** : il faut l'**historique des
prévisions** (ce qu'on prévoyait à T−24 h), pas l'historique des
observations. Un fournisseur qui ne propose que les observations passées est
inutilisable sans introduire une fuite de données.

---

## 6. Budget indicatif

| Poste | Fourchette mensuelle | Commentaire |
| --- | --- | --- |
| Cotes temps réel (agrégateur) | 30 – 250 € | Dépend du nombre de books et de la fréquence |
| Historique de cotes (achat initial) | 0 – 1 500 € **une fois** | Gratuit si cotes de clôture seulement |
| Statistiques + compos + blessures | 30 – 200 € | API généraliste |
| xG | inclus, ou 50 – 300 € | Ou maison |
| Météo | 0 € | Open-Meteo |
| **Total récurrent** | **80 – 400 €/mois** | |
| **Infrastructure (doc 12)** | **~70 €/mois** | |

> Rappel du doc 12 : les données coûtent 1 à 6 fois l'infrastructure. Les
> arbitrages budgétaires doivent porter sur les données, pas sur les
> serveurs.

---

## 7. Règles d'intégration d'un fournisseur

Quel que soit le fournisseur retenu :

| Règle | Raison |
| --- | --- |
| **Toujours deux sources pour les données bloquantes** (résultats, cotes) | Une panne ne doit pas arrêter le système |
| **Un `trust_score` par fournisseur, ajusté automatiquement** | Le taux de conflits est une mesure objective de qualité |
| **Tests de contrat par fournisseur en CI** | Un changement de format silencieux est détecté avant la production |
| **Stocker le payload brut intégral** | Permet de re-parser rétroactivement sans re-télécharger |
| **Ne jamais dépendre d'un identifiant instable** | Si le fournisseur ne garantit pas la stabilité de ses IDs, prévoir le re-matching |
| **Mesurer et publier la couverture** | « 94 % des matchs ont un xG » est une information de premier ordre pour interpréter un backtest |
| **Vérifier les conditions d'utilisation** | Le droit de stocker et de réutiliser les données varie fortement selon les contrats |

---

## 8. Le plan de collecte à lancer immédiatement

Même avant le début du développement des modèles :

```
Jour 1  : ouvrir un compte chez un agrégateur de cotes (même plan minimal)
Jour 2  : script de capture des cotes → stockage brut horodaté
Jour 3  : télécharger toutes les archives historiques gratuites disponibles
Jour 4  : capture quotidienne des calendriers, résultats, compos
Semaine 2 : capture des prévisions météo à T−72h / T−24h / T−3h
```

Ce plan coûte quelques dizaines d'euros et une poignée d'heures. Il fait
gagner **des mois** plus tard, parce qu'au moment où le modèle sera prêt,
l'historique fin existera déjà. C'est l'action à plus fort effet de levier
de tout le projet.
