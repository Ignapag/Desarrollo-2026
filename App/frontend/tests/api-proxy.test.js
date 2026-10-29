import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { onRequest } from '../functions/api/[[path]].js';

const portales = [
  'https://monu-burger-desarrollo.pages.dev',
  'https://monu-burger-clientes-desarrollo.pages.dev',
];

for (const portal of portales) {
  test(`sin API_ORIGIN usa el backend de Desarrollo desde ${portal}`, async (t) => {
    let destino;
    t.mock.method(globalThis, 'fetch', async (request) => {
      destino = request.url;
      return Response.json({});
    });
    const respuesta = await onRequest({ env: {}, request: new Request(`${portal}/api/chat-demo/sesion`, {
      method: 'POST', headers: { Cookie: 'monu_chat_demo=prueba', Origin: portal, 'X-Chat-Demo': '1' },
    }) });
    assert.equal(destino, 'https://monu-burger-desarrollo.onrender.com/api/chat-demo/sesion');
    assert.equal(respuesta.status, 200);
    assert.equal(respuesta.headers.get('cache-control'), 'private, no-store');
    assert.deepEqual(await respuesta.json(), {});
  });

  test(`el proxy conserva origen y protección del bot desde ${portal}`, async (t) => {
    const env = await backend(t, (request, response) => {
      assert.equal(request.url, '/api/chat-demo/sesion');
      assert.equal(request.method, 'POST');
      assert.equal(request.headers.origin, portal);
      assert.equal(request.headers['x-chat-demo'], '1');
      assert.equal(request.headers.cookie, 'monu_chat_demo=prueba');
      response.writeHead(200, {
        'Content-Type': 'application/json',
        'Set-Cookie': 'monu_chat_demo=prueba; HttpOnly; Secure; SameSite=Strict; Path=/api/chat-demo',
      });
      response.end('{}');
    });
    const respuesta = await onRequest({ env, request: new Request(`${portal}/api/chat-demo/sesion`, {
      method: 'POST', headers: { Cookie: 'monu_chat_demo=prueba', Origin: portal, 'X-Chat-Demo': '1' },
    }) });
    assert.equal(respuesta.status, 200);
    assert.match(respuesta.headers.get('set-cookie'), /HttpOnly; Secure; SameSite=Strict/);
    assert.deepEqual(await respuesta.json(), {});
  });
}

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
    'https://monu-burger-desarrollo.pages.dev/api/auth/login?ejemplo=1', {
      method: 'POST', headers: { Cookie: 'monu_session=prueba', 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'empleado' }),
    },
  ) });
  assert.equal(respuesta.status, 401);
  assert.equal(respuesta.headers.get('cache-control'), 'private, no-store');
  assert.match(respuesta.headers.get('set-cookie'), /HttpOnly/);
  assert.deepEqual(await respuesta.json(), { mensaje: 'Credenciales inválidas' });
});

const spoofeados = { 'X-Monu-IP-Cliente': '6.6.6.6', 'X-Monu-Proxy-Secreto': 'falso' };

test('sin secreto configurado se descartan los X-Monu-* del visitante', async (t) => {
  const env = await backend(t, (request, response) => {
    assert.equal(request.headers['x-monu-ip-cliente'], undefined);
    assert.equal(request.headers['x-monu-proxy-secreto'], undefined);
    response.end('{}');
  });
  const respuesta = await onRequest({ env, request: new Request(
    'https://monu-burger-desarrollo.pages.dev/api/auth/login',
    { headers: { ...spoofeados, 'CF-Connecting-IP': '203.0.113.7' } },
  ) });
  assert.equal(respuesta.status, 200);
});

test('con secreto y CF-Connecting-IP se envian la IP real y el secreto', async (t) => {
  const env = await backend(t, (request, response) => {
    assert.equal(request.headers['x-monu-ip-cliente'], '203.0.113.7');
    assert.equal(request.headers['x-monu-proxy-secreto'], 'secreto-compartido');
    response.end('{}');
  });
  const respuesta = await onRequest({ env: { ...env, PROXY_IP_SECRETO: 'secreto-compartido' }, request: new Request(
    'https://monu-burger-desarrollo.pages.dev/api/auth/login', { headers: { 'CF-Connecting-IP': '203.0.113.7' } },
  ) });
  assert.equal(respuesta.status, 200);
  for (const [nombre, valor] of respuesta.headers) {
    assert.ok(!nombre.startsWith('x-monu-'), nombre);
    assert.ok(!valor.includes('secreto-compartido'), nombre);
  }
});

test('X-Monu-IP-Cliente del visitante se reemplaza por CF-Connecting-IP', async (t) => {
  const env = await backend(t, (request, response) => {
    assert.equal(request.headers['x-monu-ip-cliente'], '203.0.113.7');
    assert.equal(request.headers['x-monu-proxy-secreto'], 'secreto-compartido');
    response.end('{}');
  });
  await onRequest({ env: { ...env, PROXY_IP_SECRETO: 'secreto-compartido' }, request: new Request(
    'https://monu-burger-desarrollo.pages.dev/api/auth/login',
    { headers: { ...spoofeados, 'CF-Connecting-IP': '203.0.113.7' } },
  ) });
});

test('sin CF-Connecting-IP no se envia nada aunque haya secreto', async (t) => {
  const env = await backend(t, (request, response) => {
    assert.equal(request.headers['x-monu-ip-cliente'], undefined);
    assert.equal(request.headers['x-monu-proxy-secreto'], undefined);
    response.end('{}');
  });
  await onRequest({ env: { ...env, PROXY_IP_SECRETO: 'secreto-compartido' }, request: new Request(
    'https://monu-burger-desarrollo.pages.dev/api/auth/login', { headers: spoofeados },
  ) });
});

test('el proxy no sigue redirecciones externas llevando cookies del personal', async (t) => {
  const env = await backend(t, (_, response) => {
    response.writeHead(302, { Location: 'https://example.invalid/no-se-debe-visitar' });
    response.end();
  });
  const respuesta = await onRequest({ env, request: new Request(
    'https://monu-burger-desarrollo.pages.dev/api/prueba', { headers: { Cookie: 'monu_session=prueba' } },
  ) });
  assert.equal(respuesta.status, 302);
  assert.equal(respuesta.headers.get('location'), 'https://example.invalid/no-se-debe-visitar');
});
