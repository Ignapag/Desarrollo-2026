import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createTestServer } from './vite-test-server.js';

let server, apiFetch;
const originalFetch = globalThis.fetch;
before(async () => {
  server = await createTestServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', logLevel: 'silent' });
  ({ apiFetch } = await server.ssrLoadModule('/src/shared/api/http.js'));
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); });

test('HTML con HTTP 200 no confirma una escritura', async () => {
  globalThis.fetch = async () => new Response('<html>proxy</html>', { status: 200 });
  await assert.rejects(apiFetch('/api/productos', { method: 'POST', body: '{}' }), /respuesta.*válida|confirmar/i);
});

test('un timeout libera el formulario y advierte que hay que comprobar una escritura', async () => {
  globalThis.fetch = async () => new Promise(() => {});
  await assert.rejects(apiFetch('/api/pagos', { method: 'POST', body: '{}', timeoutMs: 15 }), /tiempo.*comprob|comprob.*tiempo/i);
});

test('el plazo incluye un cuerpo JSON que nunca termina de llegar', async () => {
  globalThis.fetch = async () => ({ status: 200, ok: true, json: () => new Promise(() => {}) });
  await assert.rejects(apiFetch('/api/reportes', { timeoutMs: 15 }), /tiempo/i);
});

test('la desconexión muestra un error recuperable y nunca reenvía el POST', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new TypeError('Failed to fetch'); };
  await assert.rejects(apiFetch('/api/pagos', { method: 'POST', body: '{}' }), /conexión|conectar/i);
  assert.equal(calls, 1);
});

for (const status of [400, 401, 403, 409, 422, 429, 500, 503]) {
  test(`HTTP ${status} conserva estado y mensaje sin inventar éxito`, async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ mensaje: 'Operación rechazada' }), { status });
    await assert.rejects(apiFetch('/api/pedidos'), (error) => error.status === status && error.message === 'Operación rechazada');
  });
}

test('cancelar una petición conserva AbortError', async () => {
  const controller = new AbortController(); controller.abort();
  globalThis.fetch = async (_path, { signal }) => { signal.throwIfAborted(); };
  await assert.rejects(apiFetch('/api/productos', { signal: controller.signal }), { name: 'AbortError' });
});
