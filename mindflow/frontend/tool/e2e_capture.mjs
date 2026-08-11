// Une capture réelle, depuis un vrai navigateur, jusqu'à la base.
//
// Ce que ce fichier vérifie n'avait jamais été vérifié : le produit, servi comme
// un utilisateur le servirait, parlant à l'API comme un navigateur l'y oblige.
// Ce qui existait avant s'arrêtait juste avant la partie qui casse :
//
//   * `flutter test` ne fait aucune requête réseau ;
//   * les 896 tests serveur parlent à l'application en ASGI, sans origine, donc
//     sans CORS — et l'API n'en avait aucun pendant quatre phases ;
//   * `smoke_web.mjs` démarre la page et n'appelle jamais l'API ;
//   * aucune capture micro n'avait jamais eu lieu : le test de fumée fait
//     transiter quatre octets par IndexedDB.
//
// Prérequis : la pile locale (`../tool/dev_up.sh`) et un build web construit
// contre elle. Chromium fournit un micro synthétique — un bip, pas de la parole,
// ce qui suffit : ce qui est testé ici est le chemin, pas le modèle.
//
//   node tool/e2e_capture.mjs
//
// Les moteurs IA étant sur `fake`, la transcription rendue est une constante.
// Ce test n'affirme donc rien sur son contenu : il affirme qu'une entrée a été
// créée à partir d'octets audio produits par le navigateur.

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { loadChromium } from './browser.mjs';
import { startStaticServer } from './static_server.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', 'build', 'web');
const API = process.env.MINDFLOW_API_BASE_URL ?? 'http://127.0.0.1:8000';
const PORT = Number(process.env.PORT ?? 8902);

// Le format que le client choisit sur le web (`AudioProfile.forPlatform`).
// Épinglé ici parce que c'est la valeur qui a déjà été fausse une fois : un
// codec que Chrome refuse produit une application qui compile, s'ouvre, et
// n'enregistre rien.
const WEB_MIME = 'audio/webm;codecs=opus';

const runtime = await loadChromium();
if (!runtime) process.exit(0);
const { chromium, executablePath } = runtime;

try {
  const health = await fetch(`${API}/health`).then((r) => r.json());
  console.log(`API ${API} — ${JSON.stringify(health)}`);
} catch {
  console.error(`error: l'API ne répond pas sur ${API}. Lancez ../tool/dev_up.sh.`);
  process.exit(1);
}

const failures = [];
const check = (name, ok, detail = '') => {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

const server = await startStaticServer({ root, port: PORT });

// Le même jeton non signé que `LocalAuthRepository` fabrique côté Dart. Refusé
// hors `local` : `Settings` ne démarre pas sans méthode de vérification.
const b64url = (value) =>
  Buffer.from(JSON.stringify(value)).toString('base64url').replace(/=+$/, '');
const now = Math.floor(Date.now() / 1000);
const token = [
  b64url({ alg: 'HS256', typ: 'JWT' }),
  b64url({
    sub: '11111111-1111-4111-8111-111111111111',
    email: 'e2e@example.com',
    role: 'authenticated',
    aud: 'authenticated',
    iat: now,
    exp: now + 3600,
  }),
  'e2e',
].join('.');

const browser = await chromium.launch({
  executablePath,
  args: [
    '--no-sandbox',
    // Un micro synthétique, et l'invite d'autorisation acceptée d'office.
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
  ],
});
const context = await browser.newContext({ permissions: ['microphone'] });
await context.grantPermissions(['microphone'], { origin: server.origin });
const page = await context.newPage();
await page.goto(`${server.origin}/`, { waitUntil: 'load' });

// -- 1. Le contexte sécurisé -------------------------------------------------
//
// `getUserMedia` n'existe pas hors contexte sécurisé. Servi sur une IP de LAN
// en clair, l'objet est simplement absent — et le message d'erreur côté
// application est « micro refusé », ce qui envoie chercher au mauvais endroit.
check(
  'la page est un contexte sécurisé, donc le micro est demandable',
  await page.evaluate(() => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia),
);

check(
  `le navigateur accepte le format du client (${WEB_MIME})`,
  await page.evaluate((mime) => MediaRecorder.isTypeSupported(mime), WEB_MIME),
);

// -- 2. Le CORS, depuis la seule place d'où il est visible -------------------
const reachable = await page.evaluate(
  async ([api, bearer]) => {
    try {
      const response = await fetch(`${api}/v1/dashboard`, {
        headers: { authorization: `Bearer ${bearer}` },
      });
      return { ok: response.ok, status: response.status };
    } catch (error) {
      // Un échec CORS arrive ici, sans statut : le navigateur refuse la réponse
      // avant que le code la voie. C'est ce qui rendait l'API injoignable.
      return { ok: false, status: 0, error: String(error) };
    }
  },
  [API, token],
);
check(
  'une page servie sur une autre origine peut appeler l\'API',
  reachable.ok,
  reachable.error ?? `statut ${reachable.status}`,
);

// -- 3. La capture ----------------------------------------------------------
//
// Tout se passe dans la page : c'est le seul moyen que les octets viennent
// réellement de `MediaRecorder` et non d'un fichier que le test aurait choisi.
async function captureInPage([api, bearer, mime]) {
  // Tout est enveloppé : un refus CORS remonte ici en exception, et la laisser
  // filer rendrait une trace de pile là où il faut un diagnostic.
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream, { mimeType: mime });
    const chunks = [];
    recorder.ondataavailable = (event) => chunks.push(event.data);
    const stopped = new Promise((resolve) => (recorder.onstop = resolve));
    recorder.start();
    await new Promise((resolve) => setTimeout(resolve, 2000));
    recorder.stop();
    await stopped;
    stream.getTracks().forEach((track) => track.stop());

    const audio = new Blob(chunks, { type: mime });
    if (audio.size === 0) return { error: "MediaRecorder n'a produit aucun octet" };

    const declared = await fetch(`${api}/v1/captures`, {
      method: 'POST',
      headers: { authorization: `Bearer ${bearer}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        client_capture_id: crypto.randomUUID(),
        kind: 'quick',
        duration_ms: 2000,
        audio_format: 'webm',
        captured_at: new Date().toISOString(),
      }),
    });
    if (!declared.ok) {
      return { error: `déclaration refusée (${declared.status})`, size: audio.size };
    }
    const { data } = await declared.json();

    // Le téléversement part vers l'URL signée, cross-origin lui aussi, avec un
    // corps binaire : c'est la requête que le pré-vol CORS doit autoriser.
    const uploaded = await fetch(data.upload.url, {
      method: 'PUT',
      headers: data.upload.headers,
      body: audio,
    });
    if (!uploaded.ok) {
      return { error: `téléversement refusé (${uploaded.status})`, size: audio.size };
    }

    const completed = await fetch(`${api}/v1/captures/${data.id}/complete`, {
      method: 'POST',
      headers: { authorization: `Bearer ${bearer}` },
    });
    return { id: data.id, size: audio.size, accepted: completed.ok };
  } catch (error) {
    return { error: String(error) };
  }
}

const outcome = await page.evaluate(captureInPage, [API, token, WEB_MIME]);

check(
  'le micro produit des octets et le serveur les accepte',
  Boolean(outcome.id) && outcome.accepted,
  outcome.error ?? `${outcome.size} octets`,
);

// -- 4. Le worker les traite ------------------------------------------------
let capture = null;
if (outcome.id) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await fetch(`${API}/v1/captures/${outcome.id}`, {
      headers: { authorization: `Bearer ${token}` },
    });
    capture = (await response.json()).data;
    if (['completed', 'partially_processed', 'transcription_failed'].includes(capture.status)) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}
check(
  'la capture est traitée de bout en bout',
  capture?.status === 'completed',
  capture ? `statut ${capture.status}` : 'aucune capture',
);
check(
  'une entrée en est sortie',
  (capture?.entries?.length ?? 0) > 0,
  capture?.entries?.map((entry) => entry.entry_type).join(', ') ?? '',
);

// -- 5. Le parcours réel ----------------------------------------------------
//
// Les quatre premières parties prouvent que la plateforme et le serveur se
// parlent. Celle-ci prouve la seule chose qui intéresse un utilisateur : que
// l'application, telle qu'elle s'ouvre, enregistre une note.
//
// L'arbre d'accessibilité est le seul point de prise : CanvasKit dessine dans
// un canevas, il n'y a aucun texte dans le DOM à cliquer. Flutter le construit
// à la demande, quand le repère de sémantique est activé.
const clickLabel = (text) =>
  ui.evaluate((wanted) => {
    const node = [...document.querySelectorAll('flt-semantics')].find(
      (candidate) =>
        (candidate.getAttribute('aria-label') ?? candidate.textContent ?? '').trim() === wanted,
    );
    if (!node) return false;
    node.click();
    return true;
  }, text);

const labels = () =>
  ui.evaluate(() => [
    ...new Set(
      [...document.querySelectorAll('flt-semantics')]
        .map((node) => node.getAttribute('aria-label') ?? (node.textContent ?? '').trim())
        .filter((text) => text && text.length < 60),
    ),
  ]);

const settle = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/// Attend qu'un libellé apparaisse, plutôt qu'un délai fixe.
///
/// Écrit après coup : la première version dormait trois secondes après la
/// connexion et passait une fois sur deux. Un `sleep` calibré sur une machine au
/// repos est un test qui échoue dès que la machine travaille, et l'échec accuse
/// l'application.
async function waitForLabel(text, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if ((await labels()).includes(text)) return true;
    await settle(250);
  }
  return false;
}

/// Clique dès que la cible existe. Même raison : l'arbre d'accessibilité est
/// construit image par image, et cliquer avant qu'il porte le noeud ne fait
/// rien du tout — silencieusement.
async function clickWhenPresent(text, timeout = 30000) {
  if (!(await waitForLabel(text, timeout))) return false;
  return clickLabel(text);
}

// Une page neuve, et non un rechargement de la précédente : après un
// rechargement, Flutter ne reprend pas la main sur les champs de saisie tant
// qu'ils n'ont pas été touchés, et la connexion partait avec un formulaire
// vide. Un utilisateur ouvre l'application, il ne la recharge pas.
const ui = await context.newPage();
await ui.goto(`${server.origin}/`, { waitUntil: 'load' });
await ui.waitForSelector('flutter-view', { timeout: 60000 });
await ui.evaluate(() => document.querySelector('flt-semantics-placeholder')?.click());
await ui.waitForSelector('flt-semantics input', { timeout: 60000, state: 'attached' });

/// Saisir dans un champ Flutter.
///
/// Deux pièges, tous deux découverts en voyant le test échouer une fois sur
/// deux, et tous deux invisibles à la lecture :
///
///   * **un `locator`, pas une poignée.** Flutter recrée l'élément de saisie à
///     chaque changement de focus ; une poignée prise sur les deux champs à la
///     fois est périmée dès que le premier est rempli ;
///   * **de vraies frappes, pas un `fill`.** `fill` écrit dans `value` et émet
///     un seul événement `input` ; le moteur d'édition de Flutter ne le reprend
///     que sur le champ qu'il a lui-même activé. Le formulaire partait vide et
///     l'application répondait, à raison, « Adresse e-mail requise ».
async function typeInto(selector, text) {
  const field = ui.locator(selector).first();
  await field.click();
  await field.pressSequentially(text, { delay: 10 });
}

await typeInto('flt-semantics input[type="text"]', 'e2e@example.com');
await typeInto('flt-semantics input[type="password"]', 'motdepasse');
await clickLabel('Se connecter');
check(
  'l\'authentification locale mène au tableau de bord',
  await waitForLabel('Capturer'),
);

await clickWhenPresent('Capturer');
check(
  'l\'écran de capture propose d\'enregistrer',
  await waitForLabel('Démarrer un enregistrement'),
);

await clickWhenPresent('Démarrer un enregistrement');
check('l\'enregistrement démarre', await waitForLabel("Arrêter l'enregistrement"));

// Trois secondes de parole avant de couper : en deçà, le serveur a raison de
// répondre qu'il n'y a rien à transcrire.
await settle(3000);
await clickWhenPresent("Arrêter l'enregistrement");

// Téléversement, transcription, extraction : environ une seconde avec les
// moteurs simulés, plusieurs avec de vrais.
check('la capture aboutit dans l\'interface', await waitForLabel('Capture enregistrée', 45000));
const after = await labels();
check(
  'la transcription et ce qui en est tiré sont affichés',
  after.includes('Ce que vous avez dit') && after.includes('Ce que nous en avons tiré'),
  after.join(' | ').slice(0, 90),
);

const shot = join(root, '..', 'e2e_capture.png');
await ui.screenshot({ path: shot });
console.log(`\nCapture d'écran : ${shot}`);

await browser.close();
await server.close();

if (failures.length > 0) {
  console.error(`\n${failures.length} vérification(s) en échec.`);
  process.exit(1);
}
console.log('\nCapture réelle vérifiée de bout en bout.');
