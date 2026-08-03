# MindFlow AI — Guide d'utilisation

> Pour les personnes qui utilisent MindFlow, pas pour celles qui le
> construisent. Aucune connaissance technique supposée.

---

## 1. En une phrase

Vous parlez, MindFlow structure. Une note vocale de quinze secondes devient une
tâche avec une échéance, une décision consignée, ou une idée retrouvable — et
vous pouvez ensuite poser des questions à vos propres notes.

---

## 2. Capturer

Appuyez, parlez, relâchez. C'est tout.

- **Vous n'avez pas besoin de réseau.** La capture est enregistrée sur
  l'appareil et envoyée quand la connexion revient.
- **Vous n'avez pas besoin de bien formuler.** « Faut que je rappelle le DAF de
  Vinci jeudi » devient une tâche intitulée « Rappeler le DAF de Vinci », datée
  au jeudi suivant.
- **Vous n'avez pas besoin de vérifier tout de suite.** Ce dont MindFlow n'est
  pas sûr est marqué « à vérifier » plutôt qu'inventé.

**Ce que MindFlow ne fait jamais** : deviner une date qu'il n'a pas comprise.
S'il n'est pas certain, il vous demande en un geste plutôt que de vous donner
une échéance fausse — une mauvaise date est pire que pas de date.

---

## 3. Poser des questions

L'assistant répond à partir de **vos** notes, et seulement d'elles.

| Vous demandez | Ce qui se passe |
| --- | --- |
| « Que dois-je faire aujourd'hui ? » | Réponse immédiate, lue directement dans votre agenda |
| « Quelles sont mes tâches en retard ? » | Idem |
| « Montre les notes concernant le Forecast Gabon » | La liste, avec les dates |
| « Résume mes réunions » | Une synthèse, avec les sources en dessous |
| « Quels sujets reviennent souvent ? » | Les thèmes, comptés exactement |

**Chaque réponse rédigée cite ses sources.** Les petites étiquettes sous une
réponse sont les notes dont elle est tirée. Une réponse sans source est une
réponse que le produit ne peut pas justifier — et il vous le dit plutôt que de
faire semblant.

**S'il ne trouve pas, il le dit.** « Je ne trouve pas cette information dans vos
notes » est une réponse normale, pas une panne.

---

## 4. Travailler à plusieurs

### Les espaces

Un espace est un dossier partagé. Ce qui est **dedans** est visible par ses
membres ; ce qui est **dehors** reste strictement personnel — y compris pour
votre administrateur.

> Une note sans espace est privée. C'est le comportement par défaut : rien n'est
> partagé tant que vous ne le placez pas dans un espace.

### Les rôles

| Dans le compte | Peut |
| --- | --- |
| **Propriétaire** | Tout, y compris la facturation et la suppression du compte |
| **Administrateur** | Gérer les membres, voir le journal d'audit et les statistiques |
| **Membre** | Créer, modifier, commenter |
| **Lecteur** | Lire uniquement |

| Dans un espace | Peut |
| --- | --- |
| **Éditeur** | Modifier le contenu de l'espace |
| **Commentateur** | Commenter, sans modifier |
| **Lecteur** | Lire |

Votre rôle dans le compte et votre rôle dans un espace sont indépendants : on
peut être membre du compte et éditeur d'un seul espace.

### Commenter et mentionner

Écrivez `@prénom.nom` pour interpeller quelqu'un. Il reçoit une notification.

**Si la personne n'a pas accès à la note, MindFlow vous le dit** plutôt que de
ne rien faire : « Paul n'a pas accès à cette note ». Ajoutez-le à l'espace, et
la mention prendra effet.

Vous pouvez modifier ou supprimer **vos** commentaires. Personne ne peut
réécrire les vôtres — un administrateur peut en supprimer un, jamais le
modifier.

### Partager par lien

Un lien de partage donne accès à **une** note, en lecture, à qui l'a.

- **Les liens expirent au bout de trente jours** par défaut. Un lien collé dans
  une conversation il y a deux ans ne doit pas encore s'ouvrir.
- **Le lien n'est affiché qu'une fois.** Copiez-le tout de suite ; il n'est pas
  stocké et ne peut pas être réaffiché.
- **Vous pouvez révoquer un lien à tout moment**, et voir combien de fois il a
  été ouvert.

---

## 5. Connecter vos outils

| Service | Ce que MindFlow fait |
| --- | --- |
| **Google Calendar** | Importe vos événements ; peut y écrire vos échéances |
| **Outlook Calendar** | Idem |
| **Microsoft To Do** | Synchronise vos tâches dans les deux sens |
| **Slack** | Envoie des rappels dans un canal |
| **Microsoft Teams** | Idem |
| **Notion** | Exporte vos notes vers une base Notion |
| **Obsidian** | Écrit vos notes en Markdown dans votre coffre local |

**Par défaut, MindFlow lit et n'écrit pas.** Écrire dans votre agenda est un
choix explicite, jamais un réglage par défaut — c'est le paramètre le plus
susceptible de vous surprendre.

**Si les deux côtés changent en même temps**, MindFlow ne tranche pas tout seul.
Il vous montre le conflit et vous choisissez quelle version garder. La plupart
des produits écrasent silencieusement l'une des deux ; celui-ci demande.

**Obsidian est différent** : c'est un dossier sur votre disque, pas un service.
La synchronisation se fait par l'application, pas par le serveur — qui n'a
aucun accès à vos fichiers.

---

## 6. Ce que l'assistant retient de vous

MindFlow retient quelques **faits durables** : votre rôle, vos préférences de
réponse, qui est qui autour de vous.

- **Tout est consultable**, dans l'écran Connaissances → Mémoire.
- **Tout est supprimable en un geste**, définitivement. Ce que vous supprimez
  n'est jamais réappris.
- **Les faits anciens comptent moins.** Un fait confirmé il y a six mois est
  marqué comme ancien et pèse moins qu'un fait d'hier.

Ce qui n'est **jamais** retenu : ce que vous avez demandé pendant une
conversation, ce qui a une échéance (« en déplacement cette semaine »), et ce
qui est déjà dans vos notes.

---

## 7. Vos données

| Question | Réponse |
| --- | --- |
| Qui peut lire mes notes personnelles ? | Vous. Pas votre administrateur, pas le support |
| Où sont-elles ? | En Europe par défaut |
| Que se passe-t-il si je supprime une note ? | Elle cesse immédiatement d'apparaître, y compris dans les réponses de l'assistant |
| Puis-je exporter ? | Oui, y compris vers Obsidian en Markdown |
| Mes enregistrements servent-ils à entraîner un modèle ? | Non |

---

## 8. Questions fréquentes

**L'assistant s'est trompé.** Corrigez la note : vos corrections sont
définitives et ne sont jamais écrasées par un retraitement.

**Une note n'apparaît pas dans la recherche.** Elle vient peut-être d'être
créée. L'écran de recherche indique si l'indexation est en cours.

**J'ai perdu le lien de partage que je venais de créer.** Il n'est pas
récupérable — c'est délibéré, il n'est jamais stocké. Créez-en un autre et
révoquez l'ancien.

**Je ne peux pas me retirer d'un compte.** Si vous en êtes le dernier
propriétaire, nommez quelqu'un d'autre d'abord : un compte sans propriétaire ne
peut plus être administré par personne.
