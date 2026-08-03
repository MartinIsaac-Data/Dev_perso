# MindFlow AI — Feuille de route V3

| | |
| --- | --- |
| **Version du document** | 1.0 — écrite à la fin de la phase 4 |
| **Point de départ** | Une V2 mesurée, déployée, et utilisée par de vraies équipes |
| **Horizon** | 18 à 30 mois. **Rien ici n'est un engagement** |
| **Complément** | `RoadmapV2.md`, qui doit être terminée avant que rien de ceci ne commence |

> **Un avertissement plus fort que d'habitude.** La V2 traite de choses dont on
> connaît la forme. La V3 traite de paris. Écrire une feuille de route à
> vingt-quatre mois pour un produit qui n'a jamais eu un utilisateur est un
> exercice de cadrage, pas de planification : ce document sert à savoir **quelles
> décisions d'aujourd'hui coûteront cher demain**, pas à promettre des dates.

---

## 1. Les quatre paris

Chacun est un pari, avec une mise et une condition d'abandon. Aucun ne se lance
sans que la V2 ait répondu à ses questions.

| # | Pari | Se lance si | S'abandonne si |
| --- | --- | --- | --- |
| **P1** | La confidentialité totale est un argument de vente | Des refus commerciaux explicites sur ce motif | Personne ne le demande |
| **P2** | Le produit doit *agir*, pas seulement structurer | Les gens demandent « fais-le » | Les suggestions ne sont pas suivies |
| **P3** | Le corpus vaut plus que l'interface | La recherche est le point d'entrée principal | La capture reste l'usage dominant |
| **P4** | La plateforme vaut mieux que le produit | Des demandes d'intégration qu'on ne peut pas servir | Les sept connecteurs suffisent |

---

## 2. P1 — Le traitement local et la confidentialité de bout en bout

**Le seul pari déjà à moitié gagné.** L'interchangeabilité des fournisseurs
obtenue en phase 3 (ADR-045) fait qu'un déploiement souverain — Llama sur
matériel propre, aucune donnée sortante — est aujourd'hui une variable
d'environnement, pas un chantier.

| Étape | Contenu | Difficulté réelle |
| --- | --- | --- |
| V3.0 | Déploiement souverain documenté et testé | Faible : déjà possible, jamais fait |
| V3.1 | STT sur l'appareil pour les captures courtes | Moyenne : taille du modèle, batterie |
| V3.2 | Extraction sur l'appareil | Élevée : qualité d'un petit modèle |
| V3.3 | Chiffrement de bout en bout **optionnel** | **Le vrai sujet** |

**Le chiffrement de bout en bout casse la recherche serveur, et c'est
irréductible.** Un serveur qui ne peut pas lire ne peut pas indexer. Les trois
sorties possibles, aucune indolore :

1. **Index côté client.** Le corpus complet doit tenir sur l'appareil ; adieu la
   consultation depuis un navigateur.
2. **Chiffrement cherchable.** Fuit la structure des requêtes, et l'état de l'art
   n'est pas assez mûr pour un produit grand public.
3. **Deux modes explicites.** « Chiffré » — pas de recherche sémantique, pas
   d'assistant — et « standard ». L'utilisateur choisit, en connaissance de
   cause.

**Ma recommandation est la troisième**, et elle doit être dite ainsi à
l'utilisateur plutôt que déguisée. Un produit qui promet le chiffrement total
*et* l'assistant intelligent ment sur l'un des deux. ADR-012 avait acté le report
de ce sujet ; la V3 est le moment de le trancher, pas de le reporter encore.

---

## 3. P2 — De la structuration à l'action

Aujourd'hui, MindFlow comprend et range. Il ne fait rien.

| Étape | Ce que le produit se met à faire | Ce qui doit être vrai avant |
| --- | --- | --- |
| V3.0 | Proposer, l'utilisateur valide | Le taux de suivi des propositions est mesuré |
| V3.1 | Agir sur les intégrations existantes, avec annulation | L'écriture est fiable dans les deux sens |
| V3.2 | Agir sans confirmation sur une liste blanche | Le taux d'annulation est bas et connu |

**La règle qui gouverne tout ce chantier : une action agentique doit être
annulable, ou demander.** Créer un événement d'agenda est annulable. Envoyer un
message dans Slack ne l'est pas. Les deux ne peuvent donc pas recevoir le même
traitement, quelle que soit la confiance dans le modèle.

**Ce que le journal d'audit devient à ce moment-là.** Il consigne aujourd'hui ce
que les humains font. Dès la première action autonome, il doit consigner ce que
le produit fait *de sa propre initiative*, avec la raison — sinon la seule
réponse possible à « pourquoi a-t-il fait ça ? » est « on ne sait pas ». Le
schéma le supporte déjà : `actor_id` est nullable, et une action sans acteur
humain est exactement ce cas.

---

## 4. P3 — Le corpus comme produit

Si la recherche devient le point d'entrée principal, la valeur se déplace de la
capture vers le corpus — et les priorités avec elle.

| Étape | Contenu |
| --- | --- |
| V3.0 | Le graphe de connaissances devient navigable, pas seulement interrogeable |
| V3.1 | Détection de contradictions : deux notes qui se contredisent sont signalées |
| V3.2 | Mémoire d'équipe : ce que l'organisation sait, distinct de ce que chacun sait |
| V3.3 | Import de corpus existants — courriels, documents, historiques de messagerie |

**La détection de contradictions est la fonctionnalité la plus intéressante et la
plus dangereuse de cette liste.** « Vous aviez noté que le budget était de 40 k,
puis de 55 k » a une valeur réelle. Le même mécanisme, mal calibré, produit du
bruit permanent sur des notes qui ne se contredisent pas — et un produit qui
crie au loup s'ignore en trois jours. Seuil haut, silence par défaut.

**La mémoire d'équipe rouvre la question d'ADR-051.** La mémoire actuelle est
strictement personnelle et l'oubli y est définitif. Une mémoire partagée doit
répondre à « qui peut supprimer un fait que quelqu'un d'autre a établi ? », et
la réponse ne peut pas être « l'administrateur », sous peine de faire de la
mémoire d'équipe un outil de réécriture.

---

## 5. P4 — La plateforme

| Étape | Contenu | Point de non-retour |
| --- | --- | --- |
| V3.0 | API publique documentée et versionnée | À partir de là, on ne casse plus |
| V3.1 | Webhooks entrants | |
| V3.2 | Connecteurs tiers, via le port de synchronisation | **Le port devient un contrat public** |
| V3.3 | Extensions dans l'application | Bac à sable, permissions, revue |

**Le point de non-retour est réel.** `SyncConnectorPort` est aujourd'hui une
interface interne que l'on modifie librement. Le jour où un tiers écrit un
connecteur contre elle, chaque changement devient une rupture. Il ne faut pas
l'ouvrir avant que les sept connecteurs internes n'aient tourné en production
assez longtemps pour que ses défauts soient connus — sinon on exporte nos erreurs
et on ne peut plus les corriger.

---

## 6. Les dettes structurelles à payer en V3

Celles qui ne sont pas des fonctionnalités et qui coûteront plus cher chaque
année.

| Dette | Depuis | Ce qu'elle coûte si on la laisse |
| --- | --- | --- |
| Le monolithe modulaire (ADR-001) | Phase 0 | À ce stade, le découpage doit se décider **sur les points de contention mesurés**, pas sur les frontières supposées. Le contrat `import-linter` est ce qui rendra l'opération possible — s'il est resté vert |
| `account.data_region` inutilisé | Phase 1 | Une colonne qui promet une capacité inexistante. Soit on l'implémente, soit on la retire |
| Pas de plan de reprise après sinistre | Toujours | RTO et RPO non définis. Le premier client sérieux les demandera par écrit |
| L'audit consigne les écritures, pas les lectures | Phase 4 | Défendable aujourd'hui, refusé par un auditeur RGPD le jour d'une demande d'accès |
| Un seul propriétaire de compte peut tout | Phase 4 | Pas de séparation des pouvoirs. Une organisation de 500 personnes exigera une validation à deux |

**La première ligne est la plus importante et la moins urgente.** Le monolithe
n'est pas un problème ; c'est une décision qui a un moment de réexamen. Ce moment
arrive quand un composant précis fait souffrir les autres — vraisemblablement le
pipeline de capture, dont le profil de charge n'a rien à voir avec celui de
l'API. Le découper alors sera facile *parce que* les frontières ont été tenues
en attendant.

---

## 7. Ce qui pourrait rendre cette feuille de route caduque

Énoncé plutôt que sous-entendu.

| Événement | Effet |
| --- | --- |
| Le coût des modèles s'effondre | ADR-047 devient une optimisation prématurée. Tant mieux : elle est isolée et se retire |
| Les modèles sur appareil deviennent bons | P1 se réalise seul, et P2 devient plus sûr |
| Un acteur dominant intègre la même chose nativement | La différenciation se déplace vers ce qu'il ne fera pas : la souveraineté, l'ouverture |
| Le RGPD durcit le traitement automatisé | P2 devient beaucoup plus cher. Les actions autonomes exigeraient une base légale explicite |
| Les espaces ne servent à personne | Tout P3-V3.2 tombe, et la phase 4 reste un socle dormant |

**Ce document sera faux.** Sa fonction n'est pas d'avoir raison mais de rendre
visibles les décisions qui contraignent l'avenir — l'ouverture du port de
synchronisation, le mode chiffré, la première action autonome. Ces trois-là sont
difficiles à défaire ; tout le reste se réoriente.
