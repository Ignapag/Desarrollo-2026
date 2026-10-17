import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { onRequest } from '../functions/api/[[path]].js';

async function backend(t, handler) {
  const servidor = createServer(handler);
  servidor.listen(0, '127.0.0.1');
  await once(servidor, 'listening');
  t.after(() => { servidor.closeAllConnections(); servidor.close(); });
  return { API_ORIGIN: `http://127.0.0.1:${servidor.address().port}` };
}

test('el proxy conserva login, cookie HttpOnly, metodo, cuerpo y errores JSON', async (t) => {
  const env = await backend(t, async (request, response) => {
    assert.equal(request.url, '/api/auth/login?ejemplo=1');
    assert.equal(request.method, 'POST');
    assert.equal(request.headers.cookie, 'monu_session=prueba');
    const partes = [];
    for await (const parte of request) partes.push(parte);
    assert.deepEqual(JSON.parse(Buffer.concat(partes)), { username: 'empleado' });
    response.writeHead(401, {
      'Content-Type': 'application/json',
      'Set-Cookie': 'monu_session=; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=0',
    });
    response.end(JSON.stringify({ mensaje: 'Credenciales inválidas' }));
  });
  const respuesta = await onRequest({ env, request: new Request(
    'https://monu-burger.pages.dev/api/auth/login?ejemplo=1', {
      method: 'POST', headers: { Cookie: 'monu_session=prueba', 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'empleado' }),
    },
  ) });
  assert.equal(respuesta.status, 401);
  assert.equal(respuesta.headers.get('cache-control'), 'private, no-store');
  assert.match(respuesta.headers.get('set-cookie'), /HttpOnly/);
  assert.deepEqual(await respuesta.json(), { mensaje: 'Credenciales inválidas' });
});

test('el proxy no sigue redirecciones externas llevando cookies del personal', async (t) => {
  const env = await backend(t, (_, response) => {
    response.writeHead(302, { Location: 'https://example.invalid/no-se-debe-visitar' });
    response.end();
  });
  const respuesta = await onRequest({ env, request: new Request(
    'https://monu-burger.pages.dev/api/prueba', { headers: { Cookie: 'monu_session=prueba' } },
  ) });
  assert.equal(respuesta.status, 302);
  assert.equal(respuesta.headers.get('location'), 'https://example.invalid/no-se-debe-visitar');
});
