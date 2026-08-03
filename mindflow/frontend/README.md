# MindFlow — client Flutter

Client mobile de MindFlow AI : capture vocale, consultation des éléments
extraits, écoute de l'enregistrement d'origine.

## Écrans

| Écran | Fichier | Rôle |
|---|---|---|
| Connexion | `lib/features/auth/login_screen.dart` | Connexion / création de compte (Supabase Auth) |
| Tableau de bord | `lib/features/dashboard/dashboard_screen.dart` | Compteurs, échéances proches, quota, file d'attente hors ligne |
| Liste des notes | `lib/features/notes/notes_screen.dart` | Recherche et filtres serveur, complétion, suppression |
| Détail d'une note | `lib/features/notes/note_detail_screen.dart` | Édition, échéance, provenance |
| Enregistrement vocal | `lib/features/capture/record_screen.dart` | Micro, niveau d'entrée, envoi, suivi du traitement |
| Lecture audio | `lib/features/capture/capture_detail_screen.dart` + `audio_player.dart` | Audio d'origine, transcription, éléments extraits |

## Démarrage

Le projet ne contient que `lib/`, `test/` et `pubspec.yaml`. Les dossiers de
plateforme sont générés — ce sont des artefacts d'outil, pas du code source :

```bash
cd mindflow/frontend
flutter create --platforms=android,ios --project-name mindflow .
flutter pub get
```

### Contre la pile locale, sans projet Supabase

```bash
# depuis mindflow/ : docker compose up
flutter run \
  --dart-define=MINDFLOW_API_BASE_URL=http://10.0.2.2:8000 \
  --dart-define=MINDFLOW_LOCAL_AUTH=true
```

`MINDFLOW_LOCAL_AUTH` remplace Supabase par une identité locale qui produit le
même jeton non signé que `make_local_token` côté backend. Ce jeton est **refusé**
en staging et en production : `Settings` refuse de démarrer sans méthode de
vérification, et `TokenVerifier` ne saute la vérification de signature qu'en
`local` et `test`.

`10.0.2.2` est l'hôte vu depuis l'émulateur Android ; sur simulateur iOS,
utilisez `http://localhost:8000`.

### Contre un vrai projet Supabase

```bash
flutter run \
  --dart-define=MINDFLOW_API_BASE_URL=https://api.mindflow.ai \
  --dart-define=SUPABASE_URL=https://xxxx.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=eyJ...
```

La clé `anon` est un identifiant public, pas un secret : chaque client mobile la
porte. C'est le Row Level Security côté PostgreSQL qui protège les données.

## Tests

```bash
flutter test
```

Ce qui est couvert : le pipeline de capture et sa file d'attente hors ligne
(`capture_controller_test.dart`, `pending_capture_store_test.dart`), le décodage
du contrat API et sa tolérance aux valeurs inconnues (`models_test.dart`), la
traduction des erreurs RFC 9457 (`errors_test.dart`), le formatage des dates
(`formatting_test.dart`) et l'écran de connexion (`login_screen_test.dart`).

## Décisions structurantes

- **Riverpod** (ADR-014) : l'état est déclaratif et testable sans arbre de
  widgets — les tests du pipeline de capture instancient le contrôleur
  directement.
- **L'audio ne transite jamais par l'API** (ADR-018) : `declareCapture` renvoie
  une URL signée, le client `PUT` directement vers le stockage objet.
- **`client_capture_id` généré avant l'enregistrement** (ADR-009) : l'identité
  d'une capture existe avant ses octets, donc un rejeu après un crash désigne la
  même capture au lieu d'en créer une seconde.
- **Le fichier reste sur l'appareil** jusqu'à l'accusé de réception du serveur.
  `pending_captures.json` survit au redémarrage ; le tableau de bord rejoue la
  file au premier affichage.
- **Le quota ne bloque jamais une capture** (ADR-026) : l'interface annonce un
  traitement différé, jamais un refus.
- **Les valeurs d'énumération inconnues sont tolérées** (API.md §12.2) : le
  serveur peut en ajouter sans version majeure ; un client qui plante dessus
  transformerait un ajout en panne.
