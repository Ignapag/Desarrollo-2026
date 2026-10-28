import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let dom, server, createRoot, Provider, Bell, Notice, setUser, setInventory, tick;
const previousFetch = globalThis.fetch;
const empty = () => ({ comprobantes: [], atenciones: [], cambios: [], salidas: [] });
const data = () => ({ ...empty(), comprobantes: [{ id: 5, pedido_id: 125, numero: 125, estado: 'PENDIENTE' }], atenciones: [{ id: 6, estado: 'PENDIENTE', motivo: 'SOLICITUD' }] });
const staff = (extra = {}) => ({ id: 1, backendRole: 'EMPLEADO', permisos: ['whatsapp.ver', 'pedidos.ver', 'stock.ver'], ...extra });
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const find = (container, predicate) => elements(container, predicate);
const button = (container, name) => find(container, (node) => node.localName === 'button' && (node.textContent === name || node.getAttribute('aria-label') === name))[0];
const click = async (node) => act(async () => reactProps(node).onClick());

before(async () => {
  dom = installMinimalDom();
  const storage = new Map();
  window.localStorage = { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value), clear: () => storage.clear() };
  window.setInterval = (callback) => { tick = callback; return 1; };
  window.clearInterval = () => { tick = undefined; };
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'notificaciones-fixtures', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'let user; export const setUser=(value)=>{user=value}; export const useAuth=()=>({user});';
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return 'let state={inventory:[],inventoryStatus:"ready"}; export const setInventory=(value)=>{state=value}; const refreshInventory=async()=>{}; export const useData=()=>({state,refreshInventory});';
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ NotificationProvider: Provider } = await server.ssrLoadModule('/src/notifications/NotificationContext.jsx'));
  ({ default: Bell } = await server.ssrLoadModule('/src/notifications/NotificationBell.jsx'));
  ({ default: Notice } = await server.ssrLoadModule('/src/fulfillment/WhatsAppAttentionNotice.jsx'));
  ({ setUser } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ setInventory } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });

async function mount(t, owner = staff()) {
  window.localStorage.clear();
  setUser(owner); setInventory({ inventory: [{ id: 3, name: 'Pan', level: 'SIN_STOCK' }], inventoryStatus: 'ready' });
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const render = () => root.render(createElement(MemoryRouter, null, createElement(Provider, null, createElement(Bell), createElement(Notice))));
  await act(async () => render());
  container.rerender = async (user) => { setUser(user); await act(async () => render()); };
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); document.hidden = false; });
  return container;
}

test('contador real, apertura sin marcar leídas y lectura independiente de los pendientes', async (t) => {
  const calls = []; globalThis.fetch = async (url) => { calls.push(url); return response(data()); };
  const container = await mount(t);
  assert.ok(button(container, 'Notificaciones: 3 sin leer'));
  assert.equal(calls.length, 1);
  await click(button(container, 'Notificaciones: 3 sin leer'));
  assert.equal(calls.length, 2);
  assert.match(container.textContent, /Pan agotado/);
  await click(button(container, 'Marcar todas como leídas'));
  assert.ok(button(container, 'Notificaciones'));
  assert.match(container.textContent, /Transferencia por verificar/);
  assert.match(container.textContent, /Se necesita un empleado/);
  assert.equal(calls.length, 2);
  assert.deepEqual(find(container, (node) => node.localName === 'a' && node.textContent === 'Abrir ingrediente').map((node) => node.getAttribute('href')), ['/dashboard/inventory?ingrediente=3#ingrediente-3']);
  await click(button(container, 'Cerrar notificaciones'));
  assert.equal(find(container, (node) => node.localName === 'dialog').length, 0);
  assert.equal(document.activeElement, button(container, 'Notificaciones'));
});

test('Todas incluye revisadas; pendientes, permisos y estados vacíos se mantienen separados', async (t) => {
  globalThis.fetch = async () => response({ ...empty(), comprobantes: [{ id: 5, pedido_id: 125, estado: 'APROBADO' }] });
  const container = await mount(t, staff({ permisos: ['whatsapp.ver'] }));
  await click(button(container, 'Notificaciones: 1 sin leer'));
  assert.match(container.textContent, /No tenés notificaciones pendientes/);
  await click(button(container, 'Todas'));
  assert.match(container.textContent, /Comprobante revisado/);
  await click(button(container, 'Marcar todas como leídas'));
  assert.ok(button(container, 'Notificaciones'));
  assert.doesNotMatch(container.textContent, /Sin leer/);
  assert.equal(find(container, (node) => node.localName === 'a').length, 0);
  assert.doesNotMatch(container.textContent, /Pan agotado/);
});

test('un fallo no muestra un vacío exitoso y conserva los avisos anteriores con reintento', async (t) => {
  let fail = false;
  globalThis.fetch = async () => { if (fail) throw Error('datos privados'); return response(data()); };
  const container = await mount(t);
  fail = true;
  await click(button(container, 'Notificaciones: 3 sin leer'));
  assert.match(container.textContent, /desactualizada/);
  assert.match(container.textContent, /Transferencia por verificar/);
  assert.doesNotMatch(container.textContent, /datos privados|No tenés notificaciones pendientes/);
  fail = false;
  await click(button(container, 'Reintentar'));
  assert.doesNotMatch(container.textContent, /desactualizada/);
});

test('cambio de sesión retira datos y marcas de lectura y descarta respuestas tardías', async (t) => {
  const waiting = deferred(); let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? waiting.promise : response(empty());
  const container = await mount(t);
  await container.rerender(staff({ id: 2, permisos: ['whatsapp.ver', 'pedidos.ver'] }));
  await act(async () => waiting.resolve(response(data())));
  await click(button(container, 'Notificaciones'));
  assert.doesNotMatch(container.textContent, /Transferencia por verificar|Pan agotado/);
  assert.match(container.textContent, /No tenés notificaciones pendientes/);
});

test('sin permisos no consulta datos y con pestaña oculta no sondea', async (t) => {
  let calls = 0; globalThis.fetch = async () => { calls += 1; return response(empty()); };
  const container = await mount(t, null);
  assert.equal(calls, 0);
  assert.equal(find(container, (node) => node.localName === 'button').length, 0);
  await container.rerender(staff());
  assert.equal(calls, 1);
  document.hidden = true; await act(async () => tick());
  assert.equal(calls, 1);
});

test('el aviso de Reparto fuera del centro conserva su resumen liviano sin cargar historial', async (t) => {
  setUser(staff());
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(url); return response({ comprobantes_pendientes: 2, atenciones_pendientes: 1 }); };
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(MemoryRouter, null, createElement(Notice))));
  assert.deepEqual(calls, ['/api/whatsapp/avisos']);
  assert.match(container.textContent, /2 comprobantes/);
  assert.match(container.textContent, /Se necesita un empleado/);
});
