// Ce que la configuration Android doit contenir, faute de pouvoir la compiler.
//
// `android/` a été échafaudé sans qu'aucun APK n'ait jamais été produit : il n'y
// a pas de SDK Android ici, et Flutter n'a pas de compilation croisée. Ce script
// est donc la seule vérification automatique possible, et il ne prétend pas
// remplacer une compilation — il protège d'un mode d'échec précis et probable :
//
//   **`flutter create` régénère `android/` et efface tout ce qui a été
//   ajouté à la main.** Le manifeste retrouve ses valeurs par défaut, les
//   autorisations disparaissent, et l'application se lance parfaitement en
//   refusant d'enregistrer. C'est exactement l'argument d'ADR-060, et la raison
//   pour laquelle ce dossier est désormais du source et non de la sortie
//   d'outil.
//
//   node tool/check_android.mjs

import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'android');

const failures = [];
const check = (name, ok, detail = '') => {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

let manifest;
let gradle;
try {
  manifest = await readFile(join(root, 'app', 'src', 'main', 'AndroidManifest.xml'), 'utf8');
  gradle = await readFile(join(root, 'app', 'build.gradle'), 'utf8');
} catch (error) {
  console.error(`error: configuration Android absente — ${error.message}`);
  process.exit(1);
}

// Un manifeste mal formé fait échouer la compilation avec un message d'outil
// Android, à mille lignes de la cause.
const opened = (manifest.match(/<[a-zA-Z][^>]*[^/]>/g) ?? []).length;
const closed = (manifest.match(/<\/[a-zA-Z][^>]*>/g) ?? []).length;
const selfClosed = (manifest.match(/<[a-zA-Z][^>]*\/>/g) ?? []).length;
check(
  'le manifeste est équilibré',
  opened === closed,
  `${opened} ouvrantes, ${closed} fermantes, ${selfClosed} autonomes`,
);

const permissions = {
  'RECORD_AUDIO': "le geste du produit ; sans elle il ne reste qu'un carnet",
  'INTERNET': 'la capture part se faire transcrire',
  'POST_NOTIFICATIONS': 'exigée depuis Android 13 pour tout rappel',
  'RECEIVE_BOOT_COMPLETED': 'sans elle, un redémarrage efface les rappels programmés',
};
for (const [permission, why] of Object.entries(permissions)) {
  check(
    `autorisation ${permission}`,
    manifest.includes(`android.permission.${permission}`),
    why,
  );
}

check(
  'le récepteur de redémarrage est déclaré',
  manifest.includes('ScheduledNotificationBootReceiver') &&
    manifest.includes('android.intent.action.BOOT_COMPLETED'),
);

check(
  "l'application porte son nom",
  /android:label="MindFlow"/.test(manifest),
);

// `flutter_local_notifications` 18 ne compile pas sans désugarage : c'est la
// première chose qui casse sur un projet Flutter qui programme des rappels.
check(
  'le désugarage est activé',
  /coreLibraryDesugaringEnabled\s*=\s*true/.test(gradle) &&
    /coreLibraryDesugaring\s+["']com\.android\.tools:desugar_jdk_libs/.test(gradle),
);

const minSdk = Number(gradle.match(/minSdk\s*=\s*(\d+)/)?.[1] ?? 0);
check(
  'minSdk ≥ 23, imposé par record_android',
  minSdk >= 23,
  `minSdk = ${minSdk || 'non défini'}`,
);

if (failures.length > 0) {
  console.error(`\n${failures.length} vérification(s) en échec.`);
  process.exit(1);
}
console.log('\nConfiguration Android conforme. Elle n\'a jamais été compilée.');
