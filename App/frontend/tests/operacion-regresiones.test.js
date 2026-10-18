import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement, useLayoutEffect } from 'react';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let EditOperation;
let OrderDetail;
let DataProvider;
let useData;
let WhatsAppInbox;
const originalFetch = globalThis.fetch;
const order = { id: 17, numero: 88, version: 3, estado: 'PENDIENTE', tipo_entrega: 'DELIVERY', direccion_id: 55, metodo_pago_acordado: 'EFECTIVO', observaciones: 'Timbre 2', direccion: { id: 55, calle: 'Camino', numero: '10', localidad: 'Localidad histórica', referencia: 'Entrada lateral' }, total: '12000', saldo_pendiente: '12000', neto_cobrado: '0', items: [], pagos: [], historial: [] };
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, plugins: [
    { name: 'auth-regresiones', enforce: 'pre', load(id) {
      if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return `const user = {id: 1, role: 'admin', backendRole: 'EMPLEADO'}; export const useAuth = () => ({user});`;
      return null;
    } }, react(),
  ], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ EditOperation } = await server.ssrLoadModule('/src/fulfillment/OrderOperationForms.jsx'));
  ({ default: OrderDetail } = await server.ssrLoadModule('/src/fulfillment/OrderDetail.jsx'));
  ({ DataProvider, useData } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
  ({ default: WhatsAppInbox } = await server.ssrLoadModule('/src/fulfillment/WhatsAppInbox.jsx'));
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });

async function mount(t, Component, props, withStore = false) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(withStore ? createElement(DataProvider, null, createElement(Component, props)) : createElement(Component, props)));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
const namedField = (container, text) => elements(container, (node) => node.localName === 'label' && node.firstChild?.textContent === text)[0];
const control = (container, text) => elements(namedField(container, text), (node) => ['select', 'input', 'textarea'].includes(node.localName))[0];
const button = (container, text) => elements(container, (node) => node.localName === 'button' && node.textContent === text)[0];
async function change(node, value) { await act(async () => reactProps(node).onChange({ target: { value } })); }
async function submit(container) { await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} })); }
const response = (data) => ({ ok: true, status: 200, json: async () => data });
const completed = async (predicate) => { for (let i = 0; i < 20 && !predicate(); i += 1) await act(async () => { await new Promise((resolve) => setImmediate(resolve)); }); assert.ok(predicate(), 'La operación React debería completarse'); };

test('cambiar sólo pago conserva dirección existente y sus datos logísticos no editados', async (t) => {
  let sent;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: (_order, changes) => { sent = changes; } }, run: async (operation) => operation() });
  await change(control(container, 'Método de pago acordado'), 'TRANSFERENCIA');
  await change(control(container, 'Motivo (obligatorio)'), 'Cliente cambió el medio de pago');
  await submit(container);
  assert.deepEqual(sent, { metodo_pago_acordado: 'TRANSFERENCIA' });
});

test('cambiar sólo observaciones conserva dirección y omite los otros campos intactos', async (t) => {
  let sent;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: (_order, changes) => { sent = changes; } }, run: async (operation) => operation() });
  await change(control(container, 'Observaciones'), 'Llamar al llegar');
  await change(control(container, 'Motivo (obligatorio)'), 'Indicación del cliente');
  await submit(container);
  assert.deepEqual(sent, { observaciones: 'Llamar al llegar' });
});

test('editar el domicilio explícitamente manda sólo la dirección nueva', async (t) => {
  let sent;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: (_order, changes) => { sent = changes; } }, run: async (operation) => operation() });
  await change(control(container, 'Calle'), 'Nueva calle');
  await change(control(container, 'Motivo (obligatorio)'), 'Cliente corrigió calle');
  await submit(container);
  assert.deepEqual(sent, { direccion_nueva: { calle: 'Nueva calle', numero: '10', localidad: 'Localidad histórica', referencia: 'Entrada lateral' } });
});

test('guardar sin cambiar campos no emite una operación ni crea dirección nueva', async (t) => {
  let calls = 0;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: () => { calls += 1; } }, run: async (operation) => operation() });
  await change(control(container, 'Motivo (obligatorio)'), 'Sin cambios');
  await submit(container);
  assert.equal(calls, 0);
  assert.equal(reactProps(button(container, 'Guardar cambios')).disabled, true);
});

test('refreshData tras una revisión ignora GET anterior e inicia lectura posterior', async (t) => {
  const oldGet = deferred();
  const freshGet = deferred();
  let ordersCalls = 0;
  globalThis.fetch = async (path) => {
    if (path.startsWith('/api/pedidos')) { ordersCalls += 1; return ordersCalls === 1 ? oldGet.promise : freshGet.promise; }
    return response([]);
  };
  let data;
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  await mount(t, Capture, {}, true);
  assert.equal(ordersCalls, 1);
  let refreshed;
  // WhatsAppInbox llama refreshData después del POST de revisión confirmado.
  await act(async () => { refreshed = data.refreshData(); });
  await act(async () => { oldGet.resolve(response([order])); });
  assert.equal(ordersCalls, 2);
  assert.equal(data.state.orders.some((entry) => entry.estado === 'PENDIENTE'), false);
  await act(async () => { freshGet.resolve(response([{ ...order, version: 4, estado: 'CONFIRMADO' }])); await refreshed; });
  assert.equal(data.state.orders[0].estado, 'CONFIRMADO');
  assert.equal(data.state.orders[0].version, 4);
  assert.equal(data.state.ordersError, null);
});

test('aprobar desde WhatsAppInbox real actualiza el DataProvider con un GET posterior', async (t) => {
  const oldGet = deferred();
  const freshGet = deferred();
  let ordersCalls = 0;
  let reviews = 0;
  globalThis.fetch = async (path, options) => {
    if (path.startsWith('/api/pedidos')) { ordersCalls += 1; return ordersCalls === 1 ? oldGet.promise : freshGet.promise; }
    if (path === '/api/whatsapp/bandeja') return response({ comprobantes: [], cambios: [{ id: 9, pedido_id: 17, numero: 88, version: 3, estado: reviews ? 'APROBADO' : 'PENDIENTE_EMPLEADO', accion: { accion: 'cantidad', argumentos: { item_indice: 1, cantidad: 2 } }, anterior: { cantidad: 1, total: '12000' }, posterior: { cantidad: 2, total: '12000' } }], atenciones: [], salidas: [] });
    if (path === '/api/whatsapp/cambios/9/revision') { assert.equal(JSON.parse(options.body).aprobar, true); reviews += 1; return response({ estado: 'APROBADO' }); }
    return response([]);
  };
  let data;
  function CaptureInbox() { const current = useData(); useLayoutEffect(() => { data = current; }); return createElement(WhatsAppInbox); }
  const container = await mount(t, CaptureInbox, {}, true);
  const toggle = elements(container, (node) => node.localName === 'button' && node.textContent.includes('Bandeja de WhatsApp'))[0];
  await act(async () => reactProps(toggle).onClick());
  await change(control(container, 'Motivo y verificación realizada (obligatorio)'), 'Cliente confirmó el cambio');
  let reviewing;
  const form = elements(container, (node) => node.localName === 'form')[0];
  await act(async () => { reviewing = reactProps(form).onSubmit({ preventDefault() {}, nativeEvent: { submitter: { value: 'aprobar' } } }); });
  await completed(() => reviews === 1);
  await act(async () => { oldGet.resolve(response([order])); });
  assert.equal(ordersCalls, 2);
  assert.equal(data.state.orders.some((entry) => entry.version === 3), false);
  await act(async () => { freshGet.resolve(response([{ ...order, version: 4, estado: 'CONFIRMADO' }])); await reviewing; });
  assert.equal(data.state.orders[0].version, 4);
  assert.match(container.textContent, /Revisión registrada/);
});

for (const way of ['botón', 'Escape']) {
  test(`detalle permite salir por ${way} durante GET pendiente y aborta la consulta`, async (t) => {
    const waiting = deferred();
    let signal;
    let closed = 0;
    globalThis.fetch = async (path, options) => {
      if (path === '/api/pedidos/17') { signal = options.signal; return waiting.promise; }
      return response([]);
    };
    const container = await mount(t, OrderDetail, { id: 17, onClose: () => { closed += 1; } }, true);
    const closeButton = button(container, 'Cerrar detalle');
    if (way === 'botón') {
      assert.equal(reactProps(closeButton).disabled, false);
      await act(async () => reactProps(closeButton).onClick());
    } else {
      await act(async () => reactProps(elements(container, (node) => node.localName === 'dialog')[0]).onCancel({ preventDefault() {} }));
    }
    assert.equal(closed, 1);
    assert.equal(signal.aborted, true);
    await act(async () => { waiting.resolve(response(order)); });
    assert.doesNotMatch(container.textContent, /Pedido #88/);
  });
}

test('actualizar detalle sigue permitiendo cerrar y aborta la nueva lectura', async (t) => {
  const waiting = deferred();
  let calls = 0;
  let signal;
  let closed = 0;
  globalThis.fetch = async (path, options) => {
    if (path === '/api/pedidos/17') { calls += 1; if (calls === 1) return response({ ...order, tipo_entrega: 'RETIRO' }); signal = options.signal; return waiting.promise; }
    return response([]);
  };
  const container = await mount(t, OrderDetail, { id: 17, onClose: () => { closed += 1; } }, true);
  await act(async () => reactProps(button(container, 'Actualizar detalle')).onClick());
  assert.equal(reactProps(button(container, 'Cerrar detalle')).disabled, false);
  await act(async () => reactProps(button(container, 'Cerrar detalle')).onClick());
  assert.equal(closed, 1);
  assert.equal(signal.aborted, true);
  await act(async () => { waiting.resolve(response({ ...order, numero: 999 })); });
  assert.doesNotMatch(container.textContent, /Pedido #999/);
});

test('comando físico en curso protege el cierre; su GET posterior permite salir', async (t) => {
  const writing = deferred();
  const readingAfterWrite = deferred();
  let detailCalls = 0;
  let readSignal;
  let closed = 0;
  globalThis.fetch = async (path, options) => {
    if (path === '/api/pedidos/17') { detailCalls += 1; if (detailCalls === 1) return response({ ...order, tipo_entrega: 'RETIRO' }); readSignal = options.signal; return readingAfterWrite.promise; }
    if (path === '/api/pedidos/17/estado') return writing.promise;
    return response([]);
  };
  const container = await mount(t, OrderDetail, { id: 17, onClose: () => { closed += 1; } }, true);
  const stateForm = elements(container, (node) => node.localName === 'form' && node.textContent.includes('Estado y correcciones'))[0];
  const select = elements(stateForm, (node) => node.localName === 'select')[0];
  const reason = elements(stateForm, (node) => node.localName === 'textarea')[0];
  const confirmation = elements(stateForm, (node) => node.localName === 'input')[0];
  await change(select, 'CONFIRMADO');
  await change(reason, 'Personal confirmó');
  await act(async () => reactProps(confirmation).onChange({ target: { checked: true } }));
  await act(async () => reactProps(stateForm).onSubmit({ preventDefault() {} }));
  assert.equal(reactProps(button(container, 'Cerrar detalle')).disabled, true);
  await act(async () => reactProps(elements(container, (node) => node.localName === 'dialog')[0]).onCancel({ preventDefault() {} }));
  assert.equal(closed, 0);
  await act(async () => { writing.resolve(response({ ...order, estado: 'CONFIRMADO', version: 4, tipo_entrega: 'RETIRO' })); });
  assert.equal(reactProps(button(container, 'Cerrar detalle')).disabled, false);
  await act(async () => reactProps(button(container, 'Cerrar detalle')).onClick());
  assert.equal(closed, 1);
  assert.equal(readSignal.aborted, true);
  await act(async () => { readingAfterWrite.resolve(response({ ...order, numero: 999 })); });
  assert.doesNotMatch(container.textContent, /Pedido #999/);
});
