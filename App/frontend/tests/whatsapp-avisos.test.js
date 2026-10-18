import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let Notice;
let Inbox;
let setTestUser;
let tick;
const previousFetch = globalThis.fetch;
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const staff = () => ({ id: 1, backendRole: 'EMPLEADO', role: 'admin' });

before(async () => {
  dom = installMinimalDom();
  window.setInterval = (callback) => { tick = callback; return 1; };
  window.clearInterval = () => { tick = undefined; };
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, cacheDir: `node_modules/.vite-avisos-test-${process.pid}`, plugins: [{ name: 'sesion-avisos', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "let user; export const setTestUser=(value)=>{user=value}; export const useAuth=()=>({user});";
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return "export const useData=()=>({refreshData: async()=>{}});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Notice } = await server.ssrLoadModule('/src/fulfillment/WhatsAppAttentionNotice.jsx'));
  ({ default: Inbox } = await server.ssrLoadModule('/src/fulfillment/WhatsAppInbox.jsx'));
  ({ setTestUser } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });

async function mount(t, user = staff()) {
  setTestUser(user);
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const render = () => root.render(createElement(MemoryRouter, null, createElement(Notice)));
  await act(async () => render());
  container.rerender = async (owner) => { setTestUser(owner); await act(async () => render()); };
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); document.hidden = false; });
  return container;
}

test('muestra dos tareas distintas y cada enlace abre su sección de bandeja', async (t) => {
  const calls = [];
  globalThis.fetch = async (path) => { calls.push(path); return response({ comprobantes_pendientes: 2, atenciones_pendientes: 1 }); };
  const container = await mount(t);
  assert.deepEqual(calls, ['/api/whatsapp/avisos']);
  assert.match(container.textContent, /2 comprobantes/);
  assert.match(container.textContent, /Se necesita un empleado/);
  assert.deepEqual(elements(container, (node) => node.localName === 'a').map((link) => link.getAttribute('href')), ['/dashboard/orders?bandeja=comprobantes', '/dashboard/orders?bandeja=atenciones']);
  await act(async () => tick());
  assert.equal(elements(container, (node) => node.localName === 'a').length, 2);
});

test('al resolver tareas desaparecen sus avisos sin esconder las demás', async (t) => {
  let data = { comprobantes_pendientes: 1, atenciones_pendientes: 1 };
  globalThis.fetch = async () => response(data);
  const container = await mount(t);
  data = { comprobantes_pendientes: 0, atenciones_pendientes: 1 };
  await act(async () => tick());
  assert.equal(elements(container, (node) => node.localName === 'a').length, 1);
  data = { comprobantes_pendientes: 0, atenciones_pendientes: 0 };
  await act(async () => tick());
  assert.equal(container.textContent, '');
});

test('visitantes, clientes y repartidores no consultan tareas internas', async (t) => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return response({}); };
  const container = await mount(t, null);
  await container.rerender({ id: 2, backendRole: 'CLIENTE' });
  await container.rerender({ id: 3, backendRole: 'REPARTIDOR' });
  assert.equal(calls, 0);
  assert.equal(container.textContent, '');
});

test('un error de actualización conserva tareas y ofrece reintento', async (t) => {
  let fail = false;
  globalThis.fetch = async () => { if (fail) throw Error('Sin red'); return response({ comprobantes_pendientes: 1, atenciones_pendientes: 0 }); };
  const container = await mount(t);
  fail = true;
  await act(async () => tick());
  assert.match(container.textContent, /Comprobante por verificar/);
  assert.match(container.textContent, /No se pudieron actualizar los avisos/);
  fail = false;
  const retry = elements(container, (node) => node.localName === 'button' && node.textContent === 'Reintentar')[0];
  await act(async () => reactProps(retry).onClick());
  assert.doesNotMatch(container.textContent, /No se pudieron/);
});

test('consultas no se superponen y no se realizan con la pestaña oculta', async (t) => {
  let calls = 0;
  const waiting = deferred();
  globalThis.fetch = async () => { calls += 1; return waiting.promise; };
  await mount(t);
  await act(async () => { tick(); tick(); });
  assert.equal(calls, 1);
  await act(async () => waiting.resolve(response({ comprobantes_pendientes: 0, atenciones_pendientes: 0 })));
  document.hidden = true;
  await act(async () => tick());
  assert.equal(calls, 1);
});

test('una respuesta tardía de otra sesión no muestra tareas privadas', async (t) => {
  const waiting = deferred();
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return calls === 1 ? waiting.promise : response({ comprobantes_pendientes: 0, atenciones_pendientes: 0 }); };
  const container = await mount(t);
  await container.rerender(staff());
  await act(async () => waiting.resolve(response({ comprobantes_pendientes: 99, atenciones_pendientes: 99 })));
  assert.equal(container.textContent, '');
  assert.equal(calls, 2);
});

test('el aviso abre y enfoca su sección y permite volver a abrir la misma ruta', async (t) => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return response({ comprobantes: [], cambios: [], atenciones: [], salidas: [] }); };
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: 'primero' })));
  assert.equal(document.activeElement.textContent, 'Comprobantes');
  const toggle = elements(container, (node) => node.localName === 'button' && node.textContent === 'Bandeja de WhatsApp')[0];
  await act(async () => reactProps(toggle).onClick());
  assert.equal(reactProps(toggle)['aria-expanded'], false);
  await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: 'segundo' })));
  assert.equal(reactProps(toggle)['aria-expanded'], true);
  assert.equal(calls, 2);
  await act(async () => root.render(createElement(Inbox, { section: 'atenciones', requestKey: 'tercero' })));
  assert.equal(document.activeElement.textContent, 'Conversaciones que requieren atención');
});

test('un comprobante sin compra abre revisión manual sin botón para acreditar pago', async (t) => {
  globalThis.fetch = async () => response({ comprobantes: [], cambios: [], atenciones: [{ id: 44, motivo: 'COMPROBANTE', telefono: '5492215550000', pedido_id: null, mensaje: '', tiene_archivo: true, productos: [], mensajes: [], respuestas: [] }], salidas: [] });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: 'recibo-general' })));
  assert.match(container.textContent, /Comprobante sin pedido vinculado/);
  assert.match(container.textContent, /Descargar comprobante/);
  assert.doesNotMatch(container.textContent, /No hay comprobantes recibidos/);
  assert.equal(elements(container, (node) => node.localName === 'button' && node.textContent.includes('Aprobar')).length, 0);
  assert.equal(elements(container, (node) => node.localName === 'h4' && node.textContent.includes('Atención #44')).length, 1);
});
