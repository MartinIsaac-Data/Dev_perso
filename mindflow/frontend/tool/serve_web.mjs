// Servir le client web en développement.
//
//   node tool/serve_web.mjs [port]
//
// Pourquoi un serveur plutôt qu'ouvrir `index.html` : le micro. `getUserMedia`
// n'est accordé qu'en contexte sécurisé, c'est-à-dire HTTPS **ou** `localhost`.
// Un `file://` ou une IP de LAN en clair donnent une application qui s'ouvre,
// s'authentifie, et ne peut pas enregistrer un mot — le seul geste pour lequel
// elle existe.
//
// Servir sur `127.0.0.1` est donc un choix, pas un défaut de configuration.

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { startStaticServer } from './static_server.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'build', 'web');
const port = Number(process.argv[2] ?? process.env.PORT ?? 8080);

let server;
try {
  server = await startStaticServer({ root, port });
} catch (error) {
  console.error(`error: ${error.message}`);
  process.exit(1);
}

console.log(`MindFlow web  →  ${server.origin}`);
console.log('   Ctrl-C pour arrêter.');

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, async () => {
    await server.close();
    process.exit(0);
  });
}
