import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let Notice;
let NotificationProvider;
let Inbox;
let Orders;
let setTestUser;
let tick;
const previousFetch = globalThis.fetch;
const response = (body) => ({ ok: true, status: 200, json: async () => body?.comprobantes_pendientes == null ? body : ({
  comprobantes: Array.from({ length: body.comprobantes_pendientes }, (_, index) => ({ id: index + 1, pedido_id: index + 1, estado: 'PENDIENTE' })),
  atenciones: Array.from({ length: body.atenciones_pendientes }, (_, index) => ({ id: index + 1, motivo: 'SOLICITUD', estado: 'PENDIENTE' })), cambios: [], salidas: [],
}) });
const staff = () => ({ id: 1, backendRole: 'EMPLEADO', role: 'admin', permisos: ['pedidos.ver','whatsapp.ver','whatsapp.gestionar','whatsapp.ver_notificaciones','whatsapp.gestionar_notificaciones'] });

before(async () => {
  dom = installMinimalDom();
  window.setInterval = (callback) => { tick = callback; return 1; };
  window.clearInterval = () => { tick = undefined; };
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, cacheDir: `node_modules/.vite-avisos-test-${process.pid}`, plugins: [{ name: 'sesion-avisos', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "let user; export const setTestUser=(value)=>{user=value}; export const useAuth=()=>({user});";
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return "const state={orders:[],ordersStatus:'ready',inventory:[],inventoryStatus:'ready'}; const refreshData=async()=>{}; const refreshInventory=async()=>{}; export const useData=()=>({state,orderOperationPending:()=>false,refreshData,refreshInventory});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ NotificationProvider } = await server.ssrLoadModule('/src/notifications/NotificationContext.jsx'));
  ({ default: Notice } = await server.ssrLoadModule('/src/fulfillment/WhatsAppAttentionNotice.jsx'));
  ({ default: Inbox } = await server.ssrLoadModule('/src/fulfillment/WhatsAppInbox.jsx'));
  ({ default: Orders } = await server.ssrLoadModule('/src/fulfillment/Orders.jsx'));
  ({ setTestUser } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });

async function mount(t, user = staff()) {
  setTestUser(user);
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const render = () => root.render(createElement(MemoryRouter, null, createElement(NotificationProvider, null, createElement(Notice))));
  await act(async () => render());
  container.rerender = async (owner) => { setTestUser(owner); await act(async () => render()); };
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); document.hidden = false; });
  return container;
}

test('muestra dos tareas distintas y cada enlace abre su sección de bandeja', async (t) => {
  const calls = [];
  globalThis.fetch = async (path) => { calls.push(path); return response({ comprobantes_pendientes: 2, atenciones_pendientes: 1 }); };
  const container = await mount(t);
  assert.deepEqual(calls, ['/api/whatsapp/bandeja']);
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
  setTestUser(staff());
  await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: 'primero' })));
  assert.equal(document.activeElement.textContent, 'Comprobantes');
  const toggle = elements(container, (node) => node.localName === 'button' && node.textContent === 'Bandeja de WhatsApp')[0];
  await act(async () => reactProps(toggle).onClick());
  assert.equal(reactProps(toggle)['aria-expanded'], false);
  setTestUser(staff());
  await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: 'segundo' })));
  assert.equal(reactProps(toggle)['aria-expanded'], true);
  assert.equal(calls, 2);
  setTestUser(staff());
  await act(async () => root.render(createElement(Inbox, { section: 'atenciones', requestKey: 'tercero' })));
  assert.equal(document.activeElement.textContent, 'Conversaciones que requieren atención');
});

test('un comprobante sin compra abre revisión manual sin botón para acreditar pago', async (t) => {
  globalThis.fetch = async () => response({ comprobantes: [], cambios: [], atenciones: [{ id: 44, motivo: 'COMPROBANTE', telefono: '5492215550000', pedido_id: null, mensaje: '', tiene_archivo: true, productos: [], mensajes: [], respuestas: [] }], salidas: [] });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  setTestUser(staff());
  await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: 'recibo-general' })));
  assert.match(container.textContent, /Descargar comprobante/);
  assert.doesNotMatch(container.textContent, /No hay comprobantes recibidos/);
  assert.equal(elements(container, (node) => node.localName === 'button' && node.textContent.includes('Aprobar')).length, 0);
  assert.equal(elements(container, (node) => node.localName === 'h4' && node.textContent.includes('Atención #44')).length, 1);
});

test('buscar pedidos después de abrir un aviso no reactiva la navegación ni roba foco', async (t) => {
  globalThis.fetch = async () => response({ comprobantes: [], cambios: [], atenciones: [], salidas: [] });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  function Location() { return createElement('output', null, useLocation().search); }
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(MemoryRouter, { initialEntries: ['/dashboard/orders?bandeja=atenciones'] }, createElement(Orders), createElement(Location))));
  const input = elements(container, (node) => node.localName === 'input')[0];
  input.focus();
  await act(async () => reactProps(input).onChange({ target: { value: 'Ana' } }));
  const query = elements(container, (node) => node.localName === 'output')[0].textContent;
  assert.equal(new URLSearchParams(query).has('bandeja'), false);
  assert.equal(new URLSearchParams(query).get('q'), 'Ana');
  assert.equal(document.activeElement, input);
});

test('avisos no consulta bandeja si sólo posee permisos de notificaciones', async (t) => {
  const calls = [];
  globalThis.fetch = async (path) => { calls.push(path); return response({ comprobantes_pendientes: 1, atenciones_pendientes: 1 }); };
  const container = await mount(t, { ...staff(), permisos: ['whatsapp.ver_notificaciones'] });
  assert.deepEqual(calls, []);
  assert.equal(container.textContent, '');
});

for (const kind of ['comprobantes', 'cambios']) {
  test(`bandeja ${kind} bloquea aprobación sin permisos compuestos y conserva lectura`, async (t) => {
    const record = kind === 'comprobantes' ? { id: 92, estado: 'PENDIENTE', pedido_id: 1, numero: 1, total: '1000' } : { id: 93, estado: 'PENDIENTE_EMPLEADO', pedido_id: 1, numero: 1, anterior: { total: '1000' }, posterior: { total: '1000' } };
    const calls = [];
    setTestUser({ ...staff(), permisos: ['whatsapp.ver', 'whatsapp.gestionar'] });
    globalThis.fetch = async (path, options = {}) => { calls.push({ path, method: options.method }); return response({ comprobantes: [], cambios: [], atenciones: [], salidas: [], [kind]: [record] }); };
    const container = document.createElement('div'); document.body.appendChild(container);
    const root = createRoot(container);
    t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
    await act(async () => root.render(createElement(Inbox, { section: 'comprobantes', requestKey: kind })));
    const approve = elements(container, (node) => node.localName === 'button' && node.getAttribute('value') === 'aprobar')[0];
    assert.ok(approve); assert.equal(approve.disabled, true);
    const reason = elements(container, (node) => node.localName === 'textarea')[0];
    await act(async () => reactProps(reason).onChange({ target: { value: 'Verificado' } }));
    const check = elements(container, (node) => node.localName === 'input' && node.getAttribute('type') === 'checkbox')[0];
    if (check) await act(async () => reactProps(check).onChange({ target: { checked: true } }));
    await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {}, nativeEvent: { submitter: { value: 'aprobar' } } }));
    assert.equal(calls.some((call) => call.method === 'POST'), false);
    assert.equal(approve.disabled, true);
  });
}

test('bandeja sin gestionar sólo permite leer las conversaciones', async (t) => {
  setTestUser({ ...staff(), permisos: ['whatsapp.ver'] });
  globalThis.fetch = async () => response({ comprobantes: [], cambios: [], atenciones: [{ id: 49, motivo: 'OTRO', telefono: '5492215550000', mensaje: 'Consulta', productos: [], mensajes: [], respuestas: [] }], salidas: [] });
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(Inbox, { section: 'atenciones', requestKey: 'lectura' })));
  assert.match(container.textContent, /\+5492215550000/);
  assert.doesNotMatch(container.textContent, /Marcar como resuelta/);
});

test('atención muestra pedido, cliente y teléfono, y se cierra sólo con el botón', async (t) => {
  setTestUser(staff());
  const posts = [];
  let fail = true;
  const inbox = { comprobantes: [], cambios: [], atenciones: [{ id: 49, motivo: 'SOLICITUD', pedido_id: 7, numero: 31, cliente: 'Ana', telefono: '5492215550000', mensaje: 'Consulta', productos: [{ cantidad: 2, nombre: 'Crispy', aclaraciones: 'Sin bacon' }], mensajes: [], respuestas: [] }], salidas: [] };
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'POST') {
      posts.push({ path, body: JSON.parse(options.body) });
      if (fail) return { ok: false, status: 500, json: async () => ({ detail: 'SQL /app/private' }) };
      return response({ id: 49, estado: 'RESUELTA' });
    }
    return response(inbox);
  };
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(Inbox, { section: 'atenciones', requestKey: 'resolver' })));
  assert.match(container.textContent, /Pedido #31/);
  assert.match(container.textContent, /2 × Crispy \(Sin bacon\)/);
  assert.match(container.textContent, /Ana/);
  assert.match(container.textContent, /\+5492215550000/);
  assert.doesNotMatch(container.textContent, /Consulta|Responder por WhatsApp|Cómo se resolvió/);
  assert.equal(elements(container, (node) => node.localName === 'textarea').length, 0);
  const resolveButton = () => elements(container, (node) => node.localName === 'button' && node.textContent === 'Marcar como resuelta')[0];
  await act(async () => reactProps(resolveButton()).onClick());
  assert.match(container.textContent, /comprobá su estado|Comprobá su estado/);
  assert.doesNotMatch(container.textContent, /SQL|\/app\/private/);
  fail = false;
  await act(async () => reactProps(resolveButton()).onClick());
  assert.equal(posts.length, 2);
  assert.equal(posts[1].path, '/api/whatsapp/atenciones/49/resolucion');
  assert.ok(posts[1].body.resolucion.trim());
});

test('bandeja inesperada informa error en forma accesible y no anuncia datos vacíos', async (t) => {
  setTestUser(staff());
  globalThis.fetch = async () => response({ detail: 'datos internos' });
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(Inbox, { section: 'atenciones', requestKey: 'invalida' })));
  assert.match(container.textContent, /No pudimos cargar la bandeja/);
  assert.ok(elements(container, (node) => node.getAttribute?.('role') === 'alert').length);
  assert.doesNotMatch(container.textContent, /datos internos|No hay conversaciones/);
});

test('etiquetas de WhatsApp inesperadas usan mensajes cerrados y toleran nombres de prototipos', async (t) => {
  setTestUser(staff());
  globalThis.fetch = async () => response({ comprobantes: [], cambios: [], atenciones: [
    { id: 50, motivo: '__proto__', mensaje: 'Consulta', productos: [], respuestas: [{ id: 1, texto: 'Respuesta', estado: 'constructor' }, { id: 2, texto: 'Otra respuesta', estado: 'SQL /app/private' }], tipo_entrega: 'constructor', metodo_pago: '__proto__' },
  ], salidas: [{ id: 3, estado: 'SQL /app/private', intentos: 1 }, { id: 4, estado: '__proto__', intentos: 1 }] });
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  await act(async () => root.render(createElement(Inbox, { section: 'atenciones', requestKey: 'etiquetas-desconocidas' })));
  assert.doesNotMatch(container.textContent, /SQL|\/app\/private|__proto__|constructor/);
  assert.match(container.textContent, /Sin informar|sin informar/);
});
