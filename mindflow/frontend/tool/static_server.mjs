// Servir `build/web` comme un déploiement réel doit le faire.
//
// Deux propriétés, et elles ne sont pas décoratives :
//
//   * **repli mono-page** : toute route inconnue rend `index.html`. Sans cela un
//     lien de partage rechargé donne un 404 du serveur, alors que l'application
//     saurait parfaitement l'ouvrir ;
//   * **types MIME corrects** : un `.wasm` servi en `application/octet-stream`
//     est refusé par la compilation en flux de CanvasKit, et la page reste
//     blanche sans rien dire.
//
// Partagé entre `serve_web.mjs` (usage) et les scripts de vérification, parce
// qu'un serveur de test qui diffère du serveur de développement teste le mauvais
// serveur.

import { createServer } from 'node:http';
import { readFile, access } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.otf': 'font/otf',
  '.ttf': 'font/ttf',
  '.woff2': 'font/woff2',
  '.symbols': 'text/plain',
};

export async function assertBuildExists(root) {
  try {
    await access(join(root, 'index.html'));
  } catch {
    throw new Error(
      `build/web est absent (${root}) — lancez d'abord ./tool/build.sh web.`,
    );
  }
}

/// Démarre le serveur et rend `{ origin, close }`.
export async function startStaticServer({ root, port = 8080, host = '127.0.0.1' }) {
  await assertBuildExists(root);

  const server = createServer(async (request, response) => {
    // `normalize` puis rejet des remontées : le serveur sert un dossier, pas le
    // disque. Il ne tourne qu'en développement, ce qui est une raison de le
    // garder correct plutôt qu'une excuse.
    const requested = decodeURIComponent(request.url.split('?')[0]);
    const path = normalize(requested).replace(/^(\.\.[/\\])+/, '');
    try {
      if (path === '/' || path.includes('..')) throw new Error('index');
      const body = await readFile(join(root, path));
      response.writeHead(200, {
        'content-type': TYPES[extname(path)] ?? 'application/octet-stream',
      });
      response.end(body);
    } catch {
      response.writeHead(200, { 'content-type': TYPES['.html'] });
      response.end(await readFile(join(root, 'index.html')));
    }
  });

  await new Promise((resolve) => server.listen(port, host, resolve));
  return {
    origin: `http://${host}:${port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}
