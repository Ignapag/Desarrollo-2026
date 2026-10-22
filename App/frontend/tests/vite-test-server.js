import { createServer } from 'vite';

let nextServer = 0;

// Cada prueba tiene su caché: nunca invalida dependencias del navegador ni de otra suite.
export function createTestServer(options) {
  return createServer({
    ...options,
    cacheDir: `node_modules/.vite-tests/${process.pid}/${++nextServer}`,
  });
}
