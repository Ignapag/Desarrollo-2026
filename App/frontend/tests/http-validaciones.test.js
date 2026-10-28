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
  test(`HTTP ${status} conserva estado sin exponer diagnóstico interno`, async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ mensaje: 'SQL postgres /private/config password=secreto' }), { status });
    await assert.rejects(apiFetch('/api/pedidos'), (error) => {
      assert.equal(error.status, status);
      assert.doesNotMatch(error.message, /SQL|postgres|private|password|HTTP/);
      return true;
    });
  });
}

test('validaciones de API no exponen nombres de campos ni mensajes arbitrarios', async () => {
  globalThis.fetch = async () => Response.json({ detail: [{ loc: ['body', 'cliente_id'], msg: 'ValueError SQL interno' }] }, { status: 422 });
  await assert.rejects(apiFetch('/api/pedidos', { method: 'POST', body: '{}' }), (error) => {
    assert.doesNotMatch(error.message, /cliente_id|ValueError|SQL|body/);
    assert.match(error.message, /datos|campos/i);
    return true;
  });
});

test('origen rechazado se traduce sin exponer la protección interna', async () => {
  globalThis.fetch = async () => Response.json({ detail: 'Origen de la solicitud no permitido' }, { status: 403 });
  await assert.rejects(apiFetch('/api/chat-demo/sesion', { method: 'POST' }), /No pudimos completar la acción/);
});

test('login y conflictos conocidos tienen traducciones controladas', async () => {
  globalThis.fetch = async () => Response.json({ detail: 'credencial_interna' }, { status: 401 });
  await assert.rejects(apiFetch('/api/auth/login', { method: 'POST' }), /usuario y contraseña/);
  globalThis.fetch = async () => Response.json({ mensaje: 'Ese nombre de usuario ya existe' }, { status: 409 });
  await assert.rejects(apiFetch('/api/usuarios', { method: 'POST' }), /Ese nombre de usuario ya existe/);
});

for (const failure of [new Error('SQL interno'), new TypeError('secret token')]) {
  test(`fallo de transporte ${failure.name} conserva mensaje seguro y resultado incierto`, async () => {
    globalThis.fetch = async () => { throw failure; };
    await assert.rejects(apiFetch('/api/pagos', { method: 'POST' }), (error) => {
      assert.doesNotMatch(error.message, /SQL|secret|token/);
      assert.match(error.message, /comprob/i);
      assert.equal(error.uncertain, true);
      return true;
    });
  });
}

test('cancelar una petición conserva AbortError', async () => {
  const controller = new AbortController(); controller.abort();
  globalThis.fetch = async (_path, { signal }) => { signal.throwIfAborted(); };
  await assert.rejects(apiFetch('/api/productos', { signal: controller.signal }), { name: 'AbortError' });
});
