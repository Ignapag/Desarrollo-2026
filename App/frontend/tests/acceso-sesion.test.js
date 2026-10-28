import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement, useLayoutEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { createTestServer as createServer } from './vite-test-server.js';
import react from '@vitejs/plugin-react';
import { installMinimalDom, deferred } from './minimal-dom.js';
let server, dom, createRoot, AuthProvider, useAuth;
let apiFetch;
const previousFetch = globalThis.fetch;
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const person = { id: 1, username: 'ana', nombre: 'Ana', apellido: 'Pérez', rol: 'EMPLEADO', permisos: ['pedidos.ver'] };
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, plugins: [react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ AuthProvider, useAuth } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ apiFetch } = await server.ssrLoadModule('/src/shared/api/http.js'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });
async function mount(t) {
  let auth;
  function Capture() { const value = useAuth(); useLayoutEffect(() => { auth = value; }); return null; }
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(MemoryRouter, null, createElement(AuthProvider, null, createElement(Capture)))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return () => auth;
}
test('revalidar conserva identidad estable y actualiza permisos de una sesión abierta', async (t) => {
  let current = person;
  globalThis.fetch = async () => response(current);
  const auth = await mount(t);
  const original = auth().user;
  await act(async () => auth().refreshSession());
  assert.equal(auth().user, original);
  current = { ...person, permisos: [] };
  await act(async () => auth().refreshSession());
  assert.equal(auth().can('pedidos.ver'), false);
  assert.notEqual(auth().user, original);
});
test('un me iniciado antes de login no reemplaza al usuario nuevo', async (t) => {
  const stale = deferred();
  globalThis.fetch = async (path) => path.endsWith('/me') ? stale.promise : response({ ...person, id: 2, rol: 'ADMINISTRADOR' });
  const auth = await mount(t);
  await act(async () => auth().login('admin', 'secret'));
  assert.equal(auth().user.id, 2);
  await act(async () => stale.resolve(response(person)));
  assert.equal(auth().user.id, 2);
});
test('logout borra sesión de inmediato y descarta el me pendiente', async (t) => {
  let delay = null;
  globalThis.fetch = async (path) => path.endsWith('/me') && delay ? delay.promise : response(person);
  const auth = await mount(t);
  delay = deferred();
  let request;
  await act(async () => { request = auth().refreshSession(); });
  await act(async () => auth().logout());
  assert.equal(auth().user, null);
  await act(async () => { delay.resolve(response(person)); await request; });
  assert.equal(auth().user, null);
});

test('login espera al logout pendiente para no perder su nueva cookie', async (t) => {
  const wait = deferred(); const calls = [];
  globalThis.fetch = async (path) => { calls.push(path); return path.endsWith('/logout') ? wait.promise : response(person); };
  const auth = await mount(t);
  let exiting, entering;
  await act(async () => { exiting = auth().logout(); });
  await act(async () => { entering = auth().login('ana', 'secret'); });
  assert.equal(calls.includes('/api/auth/login'), false);
  assert.equal(auth().user, null);
  await act(async () => { wait.resolve(response(null)); await exiting; await entering; });
  assert.deepEqual(calls, ['/api/auth/me', '/api/auth/logout', '/api/auth/login']);
  assert.equal(auth().user.id, person.id);
});

test('401 de un recurso privado retira la sesión sin esperar al sondeo', async (t) => {
  globalThis.fetch = async (path) => path === '/api/pedidos' ? response({ mensaje: 'Sesión vencida' }, 401) : response(person);
  const auth = await mount(t);
  assert.equal(auth().user.id, 1);
  await act(async () => { await assert.rejects(apiFetch('/api/pedidos')); });
  assert.equal(auth().user, null);
});

test('logout fallido mantiene el cierre local, informa y permite reintentar sin restaurar la cookie vieja', async (t) => {
  let fail = true;
  globalThis.fetch = async (path) => {
    if (path.endsWith('/logout') && fail) throw new TypeError('Failed to fetch');
    return response(person);
  };
  const auth = await mount(t);
  await act(async () => { await auth().logout().catch(() => {}); });
  assert.equal(auth().user, null);
  assert.match(auth().sessionError || '', /confirmar.*cierre de sesión/i);
  await act(async () => auth().refreshSession());
  assert.equal(auth().user, null);
  fail = false;
  await act(async () => auth().logout());
  assert.equal(auth().sessionError, '');
});

test('login traduce rechazos de autenticación y no revela texto técnico desconocido', async (t) => {
  let status = 401;
  globalThis.fetch = async (path) => path.endsWith('/login')
    ? response({ detail: 'SQL password_hash /app/auth.py' }, status) : response(person);
  const auth = await mount(t);
  let result;
  await act(async () => { result = await auth().login('ana', 'secret'); });
  assert.match(result.error, /usuario y contraseña/);
  assert.equal(auth().user, null);
  status = 500;
  await act(async () => { result = await auth().login('ana', 'secret'); });
  assert.match(result.error, /No pudimos iniciar sesión/);
  assert.doesNotMatch(result.error, /SQL|password_hash|auth\.py/);
  assert.equal(auth().user, null);
});

test('una respuesta de login incompleta nunca anuncia una sesión iniciada', async (t) => {
  globalThis.fetch = async (path) => response(path.endsWith('/login') ? { rol: 'EMPLEADO' } : person);
  const auth = await mount(t);
  let result;
  await act(async () => { result = await auth().login('ana', 'secret'); });
  assert.match(result.error, /confirmar tu sesión/);
  assert.equal(result.success, undefined);
  assert.equal(auth().user, null);
});

test('la consulta inicial de sesión fallida deja un aviso seguro y una consulta exitosa lo retira', async (t) => {
  globalThis.fetch = async () => { throw new Error('SQL /app/private'); };
  const auth = await mount(t);
  assert.match(auth().sessionError, /No pudimos comprobar tu sesión/);
  assert.doesNotMatch(auth().sessionError, /SQL|private/);
  assert.equal(auth().logoutFailed, false);
  globalThis.fetch = async () => response(person);
  await act(async () => auth().refreshSession());
  assert.equal(auth().sessionError, '');
  assert.equal(auth().user.id, person.id);
});

test('el fallo de una consulta de fondo conserva la sesión vigente', async (t) => {
  globalThis.fetch = async () => response(person);
  const auth = await mount(t);
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  await act(async () => auth().refreshSession());
  assert.equal(auth().user.id, person.id);
  assert.equal(auth().sessionError, '');
});
