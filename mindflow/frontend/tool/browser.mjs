// Trouver un Chromium pilotable, sans imposer où il est installé.
//
// Playwright se présente sous trois noms selon la façon dont il a été installé —
// `playwright-core` en dépendance, `playwright` en global — et un paquet global
// n'est **pas** résolvable par un `import` : `NODE_PATH` ne s'applique qu'aux
// modules CommonJS. Un script qui ne tentait que `playwright-core` annonçait
// donc « skip » sur une machine où Playwright était installé, ce qui est la
// pire des réponses : la vérification ne tourne pas et rien ne le signale.
//
// Rend `null` quand il n'y a réellement rien, pour que l'appelant puisse passer
// son chemin avec un message clair plutôt qu'échouer.

import { execFileSync } from 'node:child_process';
import { access } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const CHROMIUM_CANDIDATES = [
  process.env.CHROME_EXECUTABLE,
  '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  '/opt/pw-browsers/chromium/chrome-linux/chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/usr/bin/google-chrome',
];

async function firstExisting(paths) {
  for (const path of paths.filter(Boolean)) {
    try {
      await access(path);
      return path;
    } catch {
      // au suivant
    }
  }
  return null;
}

function globalRoot() {
  try {
    return execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

async function loadPlaywright() {
  for (const name of ['playwright-core', 'playwright']) {
    try {
      return await import(name);
    } catch {
      // au suivant
    }
  }
  const root = globalRoot();
  if (!root) return null;
  for (const name of ['playwright-core', 'playwright']) {
    const entry = join(root, name, 'index.mjs');
    try {
      await access(entry);
      return await import(pathToFileURL(entry).href);
    } catch {
      // au suivant
    }
  }
  return null;
}

/// `{ chromium, executablePath }`, ou `null` s'il manque l'un des deux.
export async function loadChromium() {
  const playwright = await loadPlaywright();
  if (!playwright?.chromium) {
    console.log('skip: Playwright est introuvable (npm i -g playwright).');
    return null;
  }
  const executablePath = await firstExisting(CHROMIUM_CANDIDATES);
  if (!executablePath) {
    console.log('skip: aucun Chromium trouvé. Définissez CHROME_EXECUTABLE.');
    return null;
  }
  return { chromium: playwright.chromium, executablePath };
}
