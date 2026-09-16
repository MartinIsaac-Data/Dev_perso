# 02 — Catalogue complet des paramètres

> Objectif : lister tout ce qui est collectable, puis **trier brutalement**.
> Un catalogue sans hiérarchie est un piège : il pousse à collecter 300
> variables dont 260 sont du bruit corrélé, ce qui dégrade le modèle et
> multiplie les points de panne du pipeline.

---

## 0. Grille de hiérarchisation

Chaque paramètre est noté sur quatre axes :

| Axe | Signification |
| --- | --- |
| **Impact** | Gain marginal de log-loss attendu, une fois les autres variables présentes |
| **Coût** | Difficulté/prix de collecte fiable et rétroactive |
| **Fuite** | Risque que la variable ne soit pas réellement connue avant le coup d'envoi |
| **Tier** | **T1** indispensable · **T2** utile · **T3** marginal · **T4** piège |

**T4 = piège** signifie : variable qui *semble* prédictive mais qui est soit
déjà entièrement intégrée dans les autres variables, soit non disponible à
temps, soit si bruitée que son ajout dégrade le modèle. Les identifier est
aussi important que d'identifier les T1.

---

## A. Identité et contexte du match

| Paramètre | Type | Tier | Commentaire |
| --- | --- | --- | --- |
| `kickoff_utc` | timestamptz | **T1** | Clé de tout le point-in-time. Toujours en UTC + fuseau local séparé |
| `sport_id`, `competition_id`, `season_id` | FK | **T1** | Partitionne l'entraînement : ne jamais mélanger les niveaux sans effet ligue |
| `stage` (phase) | enum | **T1** | Poules / KO / barrage : la distribution des scores diffère nettement |
| `matchday` (journée) | int | T2 | Utile surtout par sa position relative en fin de saison |
| `venue_id` | FK | **T1** | Le vrai porteur de l'avantage terrain (altitude, dimensions, ambiance) |
| `is_neutral_venue` | bool | **T1** | Annule l'avantage domicile. Erreur classique en coupe |
| `surface` | enum | **T1** (tennis) / T3 (foot) | Déterminant au tennis, marginal au football |
| `home_away` | enum | **T1** | Voir la section sur l'avantage domicile |
| `attendance` / `capacity_ratio` | numeric | T3 | Endogène (les gros matchs remplissent). Connue *après* le match : **fuite** |
| `is_behind_closed_doors` | bool | **T1** quand ça arrive | Réduit l'avantage domicile d'environ un tiers (mesuré 2020-2021) |
| `match_importance` | dérivée | T2 | **Ne jamais saisir à la main** — voir section G |
| `referee_id` | FK | T2 | Pertinent uniquement pour cartons/fautes/penalties |
| `is_two_legged` / `first_leg_score` | bool / score | **T1** en coupe | Change radicalement l'incitation (une équipe peut jouer pour le 0-0) |
| `scheduled_status` | enum | **T1** | Reporté/annulé doit exclure le match du dataset, pas le compter comme nul |

---

## B. Forme récente

### B.1 Le problème des fenêtres fixes

« 5 derniers matchs » est un mauvais estimateur : c'est une moyenne mobile
non pondérée sur un échantillon minuscule (5 observations d'un processus à
forte variance). Trois défauts :

1. **Discontinuité** : le 6ᵉ match passe de poids 1 à poids 0 du jour au
   lendemain.
2. **Aucune pondération par l'adversaire** : 5 victoires contre le bas de
   tableau ≠ 5 victoires contre le haut.
3. **Aucune prise en compte du temps écoulé** : 5 matchs en 15 jours ≠ 5
   matchs en 3 mois.

### B.2 Forme pondérée par récence — la formule retenue

Décroissance exponentielle sur le **temps**, pas sur le rang du match :

```
w_i = exp( -ln(2) · Δt_i / H )
```

où `Δt_i` est le nombre de jours entre le match *i* et `as_of_ts`, et `H` la
**demi-vie** en jours. La forme pondérée d'une métrique `x` est :

```
form_x = Σ ( w_i · x_i ) / Σ w_i
```

**Choix de H par sport** (à ré-estimer par validation croisée, valeurs de
départ) :

| Sport | H (demi-vie) | Justification |
| --- | --- | --- |
| Football | 90 jours | ~12 matchs, absorbe une intersaison courte |
| Basketball NBA | 35 jours | ~15 matchs, saison dense, forme volatile |
| Tennis | 120 jours | Peu de matchs, saison par surface |

### B.3 Ajustement par la qualité de l'adversaire

La forme brute est ensuite corrigée. Pour une métrique de type « buts
marqués » :

```
x_adj_i = x_i · ( defense_rating_ligue_moyen / defense_rating_adversaire_i )
```

C'est exactement le principe des ratings attaque/défense (doc 05). En
pratique, on n'utilise **jamais** la forme brute dans le modèle : on utilise
la forme ajustée, ou directement les ratings.

### B.4 Catalogue

| Paramètre | Fenêtres | Tier | Commentaire |
| --- | --- | --- | --- |
| Points / victoires / nuls / défaites | 3, 5, 10, 15 + pondéré | T2 | Beaucoup de bruit ; dominé par les ratings |
| Buts marqués / encaissés | pondéré | **T1** | Alimente directement les λ de Poisson |
| Différence de buts | pondéré | T2 | Redondant avec les deux précédents |
| **xG pour / contre** | pondéré | **T1** | Meilleur prédicteur que les buts sur 5-15 matchs |
| Clean sheets | 10 | T3 | Fonction des buts encaissés, redondant |
| Série en cours (V/N/D) | — | **T4** | Aucun signal résiduel une fois la forme pondérée présente. Biais narratif classique |
| Forme domicile / extérieur séparée | pondéré | **T1** | Certaines équipes ont un vrai différentiel |
| Nombre de matchs dans la fenêtre | — | **T1** | Utilisé comme **mesure de fiabilité** de la forme, pas comme prédicteur |
| Buts inscrits par période (0-15, 75-90) | 10 | T3 | Utile pour les marchés « but après X » |
| % de matchs Over 2.5 | 10 | T3 | Dominé par le modèle de score lui-même |

> **Piège T4 documenté** : « l'équipe a gagné ses 6 derniers ». Une fois
> `elo_diff`, `xg_form` et `rest_days` dans le modèle, les séries n'apportent
> plus rien de mesurable. Les tester, constater, et les retirer.

---

## C. Performance avancée par sport

### C.1 Football

| Métrique | Tier | Pourquoi / piège |
| --- | --- | --- |
| **xG (for/against)** | **T1** | Le socle. Préférer un xG *sans penalty* en complément |
| xG non-penalty | **T1** | Les penalties sont très volatils et faussent la tendance |
| **xGOT** (on target) | T2 | Sépare qualité de finition et qualité de tir |
| Tirs / tirs cadrés | T2 | Largement remplacé par xG mais utile quand xG manque |
| Big chances créées/concédées | T2 | Corrélé à xG (r ≈ 0.85) — redondance |
| Possession % | T3 | **Faiblement prédictif seul.** Une possession de 70 % en bloc bas ne vaut rien |
| **PPDA** | T2 | Bon proxy d'intensité de pressing ; à normaliser par la ligue |
| Passes progressives / conduites progressives | T2 | Capturent le style de progression |
| Touches dans la surface adverse | T2 | Excellent proxy de menace soutenue |
| Corners pour/contre | **T1** pour le marché corners, T3 pour 1X2 | À modéliser par un Poisson dédié |
| Coups de pied arrêtés (xG sur CPA) | T2 | Sous-estimé ; certaines équipes en tirent 30 % de leurs buts |
| Fautes commises/subies | T2 | Entrée du modèle cartons |
| Cartons J/R | **T1** pour marché cartons | Dépend fortement de l'arbitre |
| Penalties obtenus/concédés | T3 | Très faible échantillon, forte régression à la moyenne |
| Distance parcourue / sprints | T3 | Rarement disponible rétroactivement, faible signal net |
| Âge moyen / valeur d'effectif | T2 | Proxy de niveau utile quand l'historique est court (promus) |
| Erreurs menant à un tir | T3 | Très bruité |
| Séquences de possession directes (directness) | T2 | Feature de style (voir doc sur la tactique) |

### C.2 Basketball

La normalisation par le **pace** est non négociable : un total de 118 points
ne signifie rien sans le nombre de possessions.

```
Possessions ≈ FGA − ORB + TOV + 0.44 × FTA
Pace        = 48 × (Poss_équipe + Poss_adv) / (2 × minutes_jouées)
ORtg        = 100 × Points / Possessions
DRtg        = 100 × Points encaissés / Possessions adverses
NetRtg      = ORtg − DRtg
```

| Métrique | Tier | Commentaire |
| --- | --- | --- |
| **ORtg / DRtg / NetRtg** | **T1** | Le couple fondamental |
| **Pace** | **T1** | Indispensable pour tout marché de total |
| eFG% = (FG + 0.5·3P) / FGA | **T1** | Facteur n°1 des « four factors » |
| TOV% = TOV / Poss | **T1** | Facteur n°2 |
| ORB% / DRB% | **T1** | Facteur n°3 |
| FT rate = FTA / FGA | T2 | Facteur n°4, le plus faible |
| 3PA rate, 3P% | T2 | 3P% régresse fortement : utiliser 3PA rate (stable) + 3P% attendu |
| Assist ratio | T3 | Descriptif |
| Rating quatre-facteurs ajusté adversaire | **T1** | La version brute est trompeuse |
| Minutes des cinq majeurs, ON/OFF NetRtg | **T1** | Voir Player Impact (section D) |
| Back-to-back flag | **T1** | Effet mesurable et robuste en NBA |
| Home/Road splits | T2 | Plus faible qu'au football |
| Garbage time removal | T2 | Nettoie les ratings de fin de match décidée |

### C.3 Tennis

Le tennis est structurellement différent : le résultat se dérive d'une
**chaîne de Markov sur le point servi**. Les deux seuls paramètres vraiment
nécessaires sont : `p_service_A` et `p_service_B`.

| Métrique | Tier | Commentaire |
| --- | --- | --- |
| **% points gagnés au service** | **T1** | Entrée directe du modèle |
| **% points gagnés en retour** | **T1** | = 1 − % service adverse, mais mesuré séparément pour ajuster |
| 1ʳᵉ balle % (in) | T2 | Décompose le service |
| % points gagnés sur 1ʳᵉ / 2ᵉ balle | T2 | Décomposition fine |
| Aces / doubles fautes par match de service | T2 | Marchés dédiés |
| Balles de break sauvées / converties | T3 | **Piège** : très faible échantillon, régresse massivement |
| % de jeux de service tenus (hold) | T2 | Dérivable de p_service |
| % de break | T2 | Idem |
| **Performance par surface** | **T1** | Élo par surface : dur / terre / gazon / indoor |
| Ratio victoires vs top-10/top-50 | T2 | Proxy de niveau contre l'élite |
| Historique de blessures / retraits | T2 | Un joueur qui abandonne souvent change le risque |
| Fatigue : durée des matchs précédents en minutes | **T1** | Bien meilleur que « nombre de matchs » |
| Nombre de sets joués sur 7 jours | **T1** | Idem |
| Classement ATP/WTA + points | T2 | Retardé et grossier ; Elo surface est supérieur |
| Âge, taille | T3 | Signal faible mais stable (taille ↔ service) |
| Main (droitier/gaucher), style | T3 | Effet match-up modeste |

### C.4 Métriques que le catalogue initial oubliait

| Métrique | Sport | Tier | Pourquoi elle compte |
| --- | --- | --- | --- |
| **Temps de jeu effectif** | Football | T2 | Corrélé aux totaux et aux cartons |
| **Séquence de résultats vs attentes (xPts)** | Football | **T1** | Détecte les équipes sur/sous-performantes → régression à venir |
| **Volatilité des performances** (écart-type du xG diff) | Tous | **T1** | Alimente l'intervalle de confiance, pas la moyenne |
| **Changement d'entraîneur** (date, matchs depuis) | Tous | **T1** | Rupture de série : invalide partiellement l'historique |
| **Turnover d'effectif intersaison** (% minutes conservées) | Tous | **T1** | Le meilleur correctif au début de saison |
| **Promotion/relégation** | Football | **T1** | Les promus ont un prior spécifique |
| **Jours depuis le dernier match officiel** | Tous | **T1** | Composant du score de fatigue |
| **Densité du calendrier futur** | Tous | T2 | Prédit la rotation |
| **Statut de qualification déjà acquis** | Tous | **T1** | Prédit l'implication |
| **Altitude du stade** | Foot/rugby | T2 | Effet réel au-delà de ~2000 m |
| **Distance de déplacement + fuseaux** | Tous | **T1** (NBA/NFL) | Effet documenté, surtout ouest→est |

---

## D. Joueurs, effectifs et « Player Impact on Team Strength »

### D.1 Données brutes à collecter

| Donnée | Tier | Disponibilité |
| --- | --- | --- |
| Blessure : type, date de début, retour estimé | **T1** | Fiable à J-2, bruitée avant |
| Suspension (cartons cumulés, décision disciplinaire) | **T1** | Déterministe, calculable soi-même |
| Sélection nationale / absence | T2 | Calendrier connu |
| **Composition probable** | **T1** | Source à qualité variable — traiter comme probabiliste |
| **Composition confirmée** | **T1** | T-60 min. Le run qui compte |
| Minutes jouées sur 7/14/30 jours | **T1** | Fatigue individuelle |
| Position/rôle, pied fort | T2 | Nécessaire pour valoriser le remplaçant |
| Statut « retour de blessure » (n matchs depuis) | T2 | Un joueur au retour n'est pas à 100 % |
| Âge, courbe de progression | T3 | Effet lent |
| Note de performance agrégée | T2 | Dépend du provider, à standardiser |

### D.2 Player Impact on Team Strength (PITS) — méthode

L'erreur à éviter : `impact = note_moyenne_du_joueur`. Une note individuelle
ne dit rien de ce que l'équipe perd, parce qu'elle ignore (a) le temps de jeu
réel, (b) la qualité du remplaçant, (c) la substituabilité au poste.

**Définition.** L'impact d'un joueur *p* pour l'équipe *t* est la variation
de force d'équipe entre l'effectif **avec** *p* et l'effectif **sans** *p*,
exprimée dans l'unité du modèle de score (buts attendus au football, points
pour 100 possessions au basket).

**Étape 1 — Contribution brute par 90 minutes (ou 100 possessions).**

Football : on utilise une régression ridge du différentiel de xG par minute
sur les indicatrices de présence des joueurs — l'équivalent football du
RAPM :

```
Δ_xg(segment s) = Σ_p  β_p · onfield(p, s) − Σ_q  β_q · onfield(q, s) + ε
```

estimé avec une pénalité L2 forte :

```
β̂ = argmin  Σ_s ( Δ_xg(s) − X_s β )²  +  λ ‖β‖²
```

La régularisation est **essentielle** : sans elle, les joueurs à faible temps
de jeu obtiennent des coefficients absurdes. λ est choisi par validation
croisée, et il sera grand (on veut de la régression vers zéro).

Basketball : la même chose est standard et se nomme RAPM ; on prend
directement le différentiel de points pour 100 possessions par
stint (segments à cinq joueurs constants).

**Étape 2 — Prior bayésien par poste et par niveau de ligue.**

```
β_final(p) = ( n_p · β̂_p + k · μ_poste ) / ( n_p + k )
```

où `n_p` = minutes jouées, `k` = pseudo-observations du prior (≈ 900 minutes
au football). Un joueur avec 200 minutes reste donc collé au prior de son
poste : c'est le comportement souhaité.

**Étape 3 — Impact marginal de l'absence = différence avec le remplaçant.**

```
PITS(p) = β_final(p) − β_final( remplaçant_attendu(p) )
```

`remplaçant_attendu(p)` est déterminé par un modèle de composition (voir
D.3), pas choisi à la main. C'est le point clé : **l'absence d'une superstar
remplacée par un très bon joueur coûte moins que l'absence d'un titulaire
moyen remplacé par un jeune de 19 ans à 300 minutes de carrière.**

**Étape 4 — Agrégation vers les λ du modèle de score.**

```
Δλ_attaque(équipe) = Σ_p  p_titularisation(p) · PITS_off(p) · part_minutes(p)
Δλ_défense(équipe) = Σ_p  p_titularisation(p) · PITS_def(p) · part_minutes(p)
```

puis

```
λ_ajusté = λ_base · exp( γ · Δλ_attaque )
```

La forme multiplicative-exponentielle garantit que λ reste positif et que
l'effet est proportionnel — retirer le meilleur buteur d'une équipe faible
coûte moins en valeur absolue qu'à une équipe forte.

**Étape 5 — Traduction en probabilité de victoire.**

On ne stocke jamais « −4 % de chances de gagner » en dur : on recalcule la
grille de score avec les λ ajustés et on lit la différence. Dans l'exemple du
doc 15, l'absence du buteur principal fait passer λ_dom de 1.71 à 1.62, soit
P(domicile) de 51.3 % à 49.3 % : **−2.0 points**, pas −10 comme le raconte
la presse.

**Limites à documenter dans l'interface** :
- La ridge ne sépare pas les joueurs qui jouent toujours ensemble
  (colinéarité) : deux centraux inséparables partagent leur crédit.
- L'effet d'un joueur dépend du système ; un changement d'entraîneur
  invalide partiellement les β.
- Sur les petites ligues, `n_p` est trop faible : le PITS y est dominé par le
  prior, donc quasi sans information. **Il faut l'assumer et le dire**, pas
  produire un nombre faussement précis.

### D.3 Modèle de composition probable

Un classifieur simple (régression logistique ou gradient boosting) par
joueur-match :

```
P(titulaire) = f( titularisations récentes pondérées,
                  minutes sur 14 j,
                  statut blessure,
                  suspension,
                  importance du match,
                  densité du calendrier à venir,
                  poste, concurrence au poste,
                  compo probable annoncée par la presse si disponible )
```

Ce modèle est évalué séparément (log-loss sur « titulaire oui/non ») et son
incertitude alimente le score de complétude des données.

---

## E. Tactique — transformer du qualitatif en quantitatif

**Ne jamais saisir « style = contre-attaque » à la main.** On dérive les
styles des données événementielles, ce qui donne des variables continues,
reproductibles et sans jugement d'analyste.

| Concept qualitatif | Proxy quantitatif mesurable | Source |
| --- | --- | --- |
| Intensité du pressing | PPDA, hauteur moyenne des récupérations (m) | Événements défensifs |
| Bloc haut / bas | Hauteur moyenne de la ligne défensive | Tracking ou position des actions |
| Possession de contrôle | % possession × passes par séquence | Événements de passe |
| Verticalité / directness | Progression verticale (m) par passe | Coordonnées de passes |
| Contre-attaque | % de tirs dans les 15 s suivant une récupération | Séquences |
| Build-up court | % de relances courtes du gardien | Événements |
| Transition | xG concédé dans les 10 s suivant une perte de balle | Séquences |
| Dépendance aux CPA | part du xG venant de coups de pied arrêtés | Événements |
| Largeur du jeu | % d'actions dans les couloirs | Zones |
| Formation | Vecteur de positions moyennes, puis **clustering** | Compos + positions |

**Formation : pourquoi pas un one-hot `4-3-3`.** Le libellé est instable
d'un provider à l'autre (4-3-3 vs 4-5-1 pour la même équipe). Deux options :

- *Option A* : one-hot sur le libellé fourni. Simple, mais bruité et créant
  ~20 modalités rares.
- *Option B (retenue)* : on projette l'équipe dans un espace de style à 6-8
  dimensions (les proxys ci-dessus, normalisés par ligue-saison), puis on
  applique un **k-means (k ≈ 6)** pour obtenir des archétypes appris. Les
  features utilisées sont les 6-8 coordonnées continues, pas le cluster.

**Match-up tactique.** C'est là que les interactions comptent :

```
matchup_press_vs_buildup = PPDA_adverse_inversé × short_buildup_ratio_équipe
matchup_pace             = |pace_A − pace_B|           (basket)
matchup_transition       = directness_A × ligne_haute_B
```

Ces features d'interaction sont précisément ce qu'un modèle linéaire ne peut
pas apprendre seul et ce que le gradient boosting capte bien : **c'est le
principal argument en faveur d'un GBM dans l'ensemble** (doc 05).

---

## F. Calendrier et fatigue — le Fatigue Score

### F.1 Composants

| Composant | Mesure | Poids proposé |
| --- | --- | --- |
| Charge court terme | matchs sur 3 jours (plafonné à 3) | 0.45 (dans le sous-score charge) |
| Charge moyen terme | matchs sur 7 jours (plafonné à 4) | 0.25 |
| Charge long terme | matchs sur 14 jours (plafonné à 7) | 0.10 |
| Repos | jours depuis le dernier match (saturé à 4) | 0.25 (poids global) |
| Voyage | km parcourus depuis le dernier match (saturé à 6000) | 0.12 |
| Fuseaux | |Δ heures| (saturé à 8) | 0.05 |
| Prolongations | nombre de prolongations sur 14 j (saturé à 2) | 0.03 |

### F.2 Formule

```
charge   = 0.45·min(m3,3)/3 + 0.25·min(m7,4)/4 + 0.10·min(m14,7)/7
repos    = max(0, (4 − min(rest_days,4)) / 4)
voyage   = min(km, 6000) / 6000
fuseaux  = min(|Δtz|, 8) / 8
prolong  = min(n_prolongations, 2) / 2

FatigueScore = 100 × ( 0.55·charge + 0.25·repos + 0.12·voyage
                     + 0.05·fuseaux + 0.03·prolong )
```

Exemples calculés :

| Situation | Score |
| --- | --- |
| 6 jours de repos, 1 match/7 j, aucun déplacement | **5.8** |
| 2 matchs/7 j, 3 jours de repos, 900 km | **26.9** |
| 3 matchs/7 j, 2 jours de repos, 3500 km, 3 fuseaux | **54.4** |

### F.3 Limites — à lire avant d'utiliser ce score

1. **Les poids sont des priors, pas des estimations.** Ils doivent être
   remplacés par des coefficients appris dès qu'on dispose de ~2 saisons.
   La version « experte » sert de point de départ et de garde-fou.
2. **La fatigue d'équipe n'est pas la fatigue des joueurs.** Une équipe à
   effectif profond fait tourner : le score doit être pondéré par la
   profondeur d'effectif, sinon on pénalise à tort les grands clubs. Feature
   correctrice : `squad_depth` = nombre de joueurs au-dessus d'un seuil de
   PITS.
3. **Effet non linéaire et asymétrique.** 2 jours de repos vs 3 est un écart
   énorme ; 8 vs 9 est nul. Les saturations le gèrent grossièrement ; un GBM
   apprendra mieux la forme exacte s'il reçoit les composants bruts.
4. **Risque de double comptage** : si le score de fatigue *et* ses composants
   bruts entrent dans le modèle, le GBM utilisera les composants et le score
   agrégé deviendra du bruit corrélé. **Décision : les composants bruts
   entrent dans le modèle ML ; le score agrégé n'est utilisé que pour
   l'affichage et pour le modèle statistique.**
5. **Le marché connaît le calendrier.** Un back-to-back NBA est intégré dans
   la cote. La fatigue n'est source de value que dans ses cas *atypiques*
   (voyage inhabituel, prolongation récente, cumul coupe + championnat).

---

## G. Contexte et enjeu — sans inventer de « motivation 8/10 »

**Règle absolue : aucune variable subjective.** On remplace « motivation »
par des quantités calculables à partir du classement et du calendrier.

| Feature | Calcul |
| --- | --- |
| `p_title` | Probabilité de titre par **simulation Monte-Carlo** du reste de la saison (10 000 tirages avec le modèle lui-même) |
| `p_qualification_euro` | Idem, pour chaque place qualificative |
| `p_relegation` | Idem |
| **`stakes_swing`** | **Écart de probabilité d'objectif entre gagner et perdre ce match** : `|p_objectif(V) − p_objectif(D)|`. C'est la vraie mesure d'enjeu |
| `is_dead_rubber` | `stakes_swing < ε` pour les **deux** équipes |
| `days_to_next_important_match` | Distance au prochain match à `stakes_swing` élevé |
| `competing_competition_priority` | `stakes_swing` du prochain match dans une autre compétition ÷ `stakes_swing` de celui-ci |
| `is_derby` | Table de faits : distance géographique < 30 km **ou** rivalité déclarée |
| `h2h_recent_intensity` | Cartons + fautes dans les 5 dernières confrontations (marché cartons) |
| `is_second_leg` + `aggregate_state` | Différence de buts cumulée avant le match |
| `must_win_margin` | Nombre de buts nécessaires pour se qualifier (0 si simple victoire suffit) |

`stakes_swing` est la feature qui remplace toute notion de motivation : elle
est objective, calculable, et elle capte exactement le phénomène qu'on
cherche (« ce match change-t-il quelque chose pour eux ? »). Elle est
naturellement nulle en fin de saison pour les équipes de milieu de tableau —
ce qui est le cas où la rotation explose.

**Le piège majeur** : ces variables sont fortement **non linéaires et
interactives**. Une équipe déjà qualifiée à 100 % qui affronte une équipe en
lutte pour le maintien lors de la dernière journée est un cas extrême, très
rare dans les données. Avec 3 saisons d'historique, il y en aura peut-être
40 exemples. **Conclusion : ne pas laisser le ML apprendre cela seul.**
Utiliser une correction explicite et bornée, dont l'amplitude est un
hyperparamètre validé sur backtest, et l'afficher comme un ajustement séparé
dans l'explication.

---

## H. Facteurs environnementaux — lesquels méritent d'entrer

| Facteur | Effet documenté | Tier | Décision |
| --- | --- | --- | --- |
| Pluie forte / terrain détrempé | Baisse modeste des buts, hausse des erreurs | T2 | **Inclure** en seuils (mm/h > 4) |
| Vent > 30 km/h | Baisse de la précision des passes longues et des tirs lointains | T2 | **Inclure** (seuil) |
| Température < 0 °C ou > 32 °C | Baisse du rythme et de la distance parcourue | T2 | **Inclure** (écart à 15 °C, quadratique) |
| Neige | Effet fort mais très rare | T3 | Inclure en flag |
| Humidité | Effet marginal isolément | T3 | Ne pas inclure seul ; interagit avec la température |
| **Altitude > 1500 m** | Effet réel et fort pour l'équipe non acclimatée | **T1** (Amérique du Sud, Mexique) | **Inclure** + `altitude_diff` avec le stade habituel de l'adversaire |
| État de la pelouse | Effet plausible | T3 | Rarement disponible de façon fiable ; **exclure** en V1 |
| Affluence | Endogène + connue après coup | **T4** | **Exclure** — risque de fuite |
| Huis clos | Réduction nette de l'avantage domicile | **T1** | **Inclure** |
| Surface (tennis) | Déterminant | **T1** | **Inclure** via des Elo séparés |
| Terrain synthétique (foot) | Effet faible mais réel sur les équipes visiteuses | T3 | Inclure en flag |

**Verdict général sur la météo au football** : l'effet net, une fois les
ratings dans le modèle, est **petit** — de l'ordre de 0.02 à 0.05 but sur
le total attendu, sauf conditions extrêmes. La météo mérite d'être collectée
(elle est gratuite ou quasi) et intégrée au modèle de totaux, mais **elle
n'est presque jamais une source de value** : les bookmakers la regardent
aussi. Elle est incluse pour ne pas être *en retard* sur le marché, pas pour
le battre.

Point technique qui compte : **on stocke la prévision telle qu'elle était à
T-24h et à T-3h, pas l'observation réelle du match**. Utiliser la météo
observée est une fuite de données caractérisée.

---

## I. Arbitres

| Métrique arbitre | Fenêtre | Marchés concernés |
| --- | --- | --- |
| Cartons jaunes / match | 40 derniers matchs, pondéré | **Cartons** (T1), corners (non) |
| Cartons rouges / match | 80 matchs | Cartons (T2) |
| Penalties sifflés / match | 80 matchs | Penalties, BTTS (faible), 1X2 (non) |
| Fautes sifflées / match | 40 matchs | Cartons, fautes |
| Écart-type des cartons | 40 matchs | **Variance** du marché cartons |
| Biais domicile (Δ cartons dom/ext) | 80 matchs | Cartons asiatiques |
| Niveau de compétition arbitré | — | Normalisation |

**Point de méthode important** : un arbitre « sévère » l'est en partie parce
qu'on lui confie les matchs chauds. Il faut donc estimer la tendance
arbitrale **nette de la nature des matchs arbitrés** : régression des cartons
sur (intensité attendue du match, niveau, derby) + effet aléatoire arbitre.
Sinon, on attribue à l'arbitre ce qui appartient au match.

**Pertinence par marché** :

| Marché | L'arbitre compte-t-il ? |
| --- | --- |
| Cartons (over/under, asiatique) | **Oui, fortement** — c'est la variable n°2 après l'intensité du match |
| Fautes | Oui |
| Penalties | Modérément (faible échantillon) |
| BTTS / Over-Under buts | Très marginalement (via les penalties) |
| 1X2 | **Non** — ne pas l'inclure, c'est du bruit |
| Corners | Non |

---

## J. Head-to-head (H2H) — pourquoi « les 5 dernières confrontations » est une erreur

### J.1 Les trois défauts

1. **Échantillon minuscule.** 5 matchs, souvent étalés sur 5 ans, avec des
   effectifs et des entraîneurs différents. Le signal est noyé.
2. **Double comptage.** Si l'équipe A bat systématiquement B, c'est presque
   toujours parce que A est meilleure — information déjà contenue dans les
   ratings. Ajouter le H2H brut revient à compter deux fois la même chose.
3. **Biais de sélection.** Deux équipes ne se rencontrent que dans certaines
   compétitions ; l'échantillon H2H n'est pas représentatif.

### J.2 H2H pondéré — la formulation retenue

On ne prédit pas *avec* le H2H : on mesure un **résidu** H2H, c'est-à-dire
ce que les confrontations passées disent **au-delà** de ce que les ratings
prédisaient déjà.

```
Pour chaque confrontation i :
    résidu_i = résultat_observé_i − résultat_attendu_par_le_modèle_à_l'époque_i
```

(en unités de différence de buts, ou de log-odds pour le 1X2)

Poids composite :

```
w_i = w_récence · w_continuité · w_contexte

w_récence     = exp(−ln2 · Δt_i / 540 jours)       # demi-vie 18 mois
w_continuité  = 0.5 · continuité_effectif_A(i)      # % de minutes conservées
              + 0.5 · continuité_effectif_B(i)
              × (1 si même entraîneur des deux côtés, 0.6 sinon)
w_contexte    = 1.0 si même compétition et même lieu (dom/ext)
              = 0.7 si même compétition, lieu inversé
              = 0.5 si compétition différente
              = 0.3 si terrain neutre vs non neutre

h2h_residual = Σ(w_i · résidu_i) / Σ(w_i)
h2h_weight   = Σ(w_i)          # masse d'information disponible
```

Le modèle reçoit **deux** features : `h2h_residual` et `h2h_weight`. La
seconde permet au modèle d'apprendre lui-même à ignorer le résidu quand la
masse est faible — bien mieux qu'un seuil arbitraire.

### J.3 Quand ne PAS utiliser le H2H

| Situation | Pourquoi |
| --- | --- |
| `h2h_weight < 1.5` (moins de ~2 confrontations effectives) | Pur bruit |
| Changement d'entraîneur d'un côté depuis la dernière rencontre | L'objet mesuré n'existe plus |
| Turnover d'effectif > 40 % | Idem |
| Équipe promue / première rencontre | Aucune donnée |
| **Tennis** | Sauf cas particulier (style très asymétrique, ex. gros serveur vs relanceur d'élite), le H2H tennis est dominé par les Elo de surface. L'effet net résiduel mesuré est proche de zéro |
| Basketball NBA | Les rosters changent trop vite ; H2H quasi inutile au-delà de la même saison |
| Marchés de totaux | Le H2H de totaux est presque entièrement expliqué par les styles actuels |

**Conclusion honnête** : après contrôle par les ratings, le H2H apporte un
gain de log-loss faible (typiquement < 0.3 %) au football et nul ailleurs. Il
est conservé parce qu'il est peu coûteux et parce que les utilisateurs
l'attendent dans l'interface — mais il est affiché comme **information
descriptive**, avec un poids de modèle affiché honnêtement.

---

## K. Synthèse : le top 15 par impact réel (football, marché 1X2)

Classement attendu, à vérifier empiriquement par ablation (doc 07) :

| Rang | Feature | Famille |
| --- | --- | --- |
| 1 | `market_prob_devig` (si l'on s'autorise le marché) | Marché |
| 2 | `elo_diff` / `rating_attack_diff`, `rating_defense_diff` | Rating |
| 3 | `xg_form_weighted_diff` (pour et contre) | Forme avancée |
| 4 | `home_advantage_competition` | Contexte |
| 5 | `pits_unavailable_sum` (impact des absents) | Effectif |
| 6 | `squad_continuity` / changement d'entraîneur | Effectif |
| 7 | `rest_days`, `matches_7d` | Fatigue |
| 8 | `stakes_swing` (les deux équipes) | Enjeu |
| 9 | `xpts_overperformance` (régression à venir) | Forme avancée |
| 10 | `promoted_flag` / niveau de ligue précédent | Contexte |
| 11 | `style_matchup_*` (interactions) | Tactique |
| 12 | `travel_km`, `tz_shift` | Fatigue |
| 13 | `venue_altitude_diff` | Environnement |
| 14 | `h2h_residual` × `h2h_weight` | H2H |
| 15 | Météo extrême (flags) | Environnement |

Et la liste des **T4 à ne pas inclure** : séries en cours, affluence,
possession brute, « forme » en points non ajustée, classement brut, notes
de journalistes, statistiques de la saison en cours en début de saison
(< 6 matchs) sans shrinkage vers la saison précédente.
