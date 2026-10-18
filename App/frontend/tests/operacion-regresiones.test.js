import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement, useLayoutEffect, useState } from 'react';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let EditOperation;
let StateOperation;
let OrderPayments;
let OrderDelivery;
let OrderDetail;
let DataProvider;
let useData;
let WhatsAppInbox;
let Kitchen;
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
  ({ EditOperation, StateOperation } = await server.ssrLoadModule('/src/fulfillment/OrderOperationForms.jsx'));
  ({ default: OrderPayments } = await server.ssrLoadModule('/src/fulfillment/OrderPayments.jsx'));
  ({ default: OrderDelivery } = await server.ssrLoadModule('/src/fulfillment/OrderDelivery.jsx'));
  ({ default: OrderDetail } = await server.ssrLoadModule('/src/fulfillment/OrderDetail.jsx'));
  ({ DataProvider, useData } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
  ({ default: WhatsAppInbox } = await server.ssrLoadModule('/src/fulfillment/WhatsAppInbox.jsx'));
  ({ default: Kitchen } = await server.ssrLoadModule('/src/kitchen/Kitchen.jsx'));
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
  await submit(container);
  assert.deepEqual(sent, { metodo_pago_acordado: 'TRANSFERENCIA' });
});

test('cambiar sólo observaciones conserva dirección y omite los otros campos intactos', async (t) => {
  let sent;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: (_order, changes) => { sent = changes; } }, run: async (operation) => operation() });
  await change(control(container, 'Observaciones'), 'Llamar al llegar');
  await submit(container);
  assert.deepEqual(sent, { observaciones: 'Llamar al llegar' });
});

test('editar el domicilio explícitamente manda sólo la dirección nueva', async (t) => {
  let sent;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: (_order, changes) => { sent = changes; } }, run: async (operation) => operation() });
  await change(control(container, 'Calle'), 'Nueva calle');
  await submit(container);
  assert.deepEqual(sent, { direccion_nueva: { calle: 'Nueva calle', numero: '10', localidad: 'Localidad histórica', referencia: 'Entrada lateral' } });
});

test('guardar sin cambiar campos no emite una operación ni crea dirección nueva', async (t) => {
  let calls = 0;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', busy: false, commands: { edit: () => { calls += 1; } }, run: async (operation) => operation() });
  await submit(container);
  assert.equal(calls, 0);
  assert.equal(reactProps(button(container, 'Guardar cambios')).disabled, true);
});

test('enviar a cocina es una acción directa sin motivo ni casilla, con registro automático', async (t) => {
  let sent;
  const container = await mount(t, StateOperation, { order, role: 'EMPLEADO', busy: false,
    commands: { state: (current, command, reason) => { sent = { current, command, reason }; } }, run: async (operation) => operation() });
  const cook = button(container, 'Enviar a cocina');
  assert.ok(cook, 'La acción principal debe ser un botón directo');
  await act(async () => reactProps(cook).onClick());
  assert.equal(sent.current.id, order.id);
  assert.equal(sent.command.estado, 'EN_PREPARACION');
  assert.match(sent.reason, /cocina/i);
  assert.equal(elements(container, (node) => node.localName === 'input' && reactProps(node).type === 'checkbox').length, 0);
});

test('cancelar pide una sola confirmación contextual y conserva el tratamiento de stock', async (t) => {
  const calls = [];
  const container = await mount(t, StateOperation, { order: { ...order, estado: 'EN_PREPARACION' }, role: 'EMPLEADO', busy: false,
    commands: { state: (_order, command, reason) => { calls.push({ command, reason }); } }, run: async (operation) => operation() });
  assert.ok(button(container, 'Cancelar pedido'));
  await act(async () => reactProps(button(container, 'Cancelar pedido')).onClick());
  assert.equal(calls.length, 0);
  assert.match(container.textContent, /merma/i);
  await act(async () => reactProps(button(container, 'Confirmar cancelación')).onClick());
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command.tratamiento_stock, 'MERMA');
  assert.ok(calls[0].reason.trim());
});

test('cobro exacto usa el saldo preparado sin completar campos ni confirmar casillas', async (t) => {
  let sent;
  globalThis.fetch = async (path, options) => { sent = { path, body: JSON.parse(options.body) }; return response({ id: 51, estado: 'CONCILIADO' }); };
  const container = await mount(t, OrderPayments, { order, userId: 1, commands: {}, busy: false, run: async (operation) => operation() });
  await submit(container);
  assert.equal(sent?.path, '/api/pagos/efectivo?incluir_pedido=true');
  assert.equal(sent.body.monto_recibido, '12000');
  assert.equal(sent.body.monto_a_pagar, '12000');
  assert.equal(sent.body.conciliar_inmediato, true);
  assert.ok(sent.body.clave_operacion);
});

test('transferencia ya pendiente se confirma por su ID sin crear otro cobro', async (t) => {
  const calls = [];
  const transferOrder = { ...order, metodo_pago_acordado: 'TRANSFERENCIA', pagos: [{ id: 73, tipo: 'COBRO', estado: 'PENDIENTE', metodo_pago: 'TRANSFERENCIA', monto: '12000' }] };
  const container = await mount(t, OrderPayments, { order: transferOrder, userId: 1, busy: false,
    commands: { reconcile: (id) => { calls.push(id); } }, run: async (operation) => operation() });
  const confirm = elements(container, (node) => node.localName === 'button' && node.textContent.startsWith('Confirmar ingreso de'))[0];
  assert.ok(confirm);
  await act(async () => reactProps(confirm).onClick());
  assert.deepEqual(calls, [73]);
});

test('efectivo registrado pendiente se concilia por su ID sin crear otro cobro', async (t) => {
  const calls = [];
  const cashOrder = { ...order, pagos: [{ id: 74, tipo: 'COBRO', estado: 'PENDIENTE', metodo_pago: 'EFECTIVO', monto: '12000' }] };
  const container = await mount(t, OrderPayments, { order: cashOrder, userId: 1, busy: false,
    commands: { reconcile: (id) => { calls.push(id); } }, run: async (operation) => operation() });
  const confirm = elements(container, (node) => node.localName === 'button' && node.textContent.startsWith('Confirmar ingreso de'))[0];
  assert.ok(confirm, 'El cobro pendiente existente debe poder confirmarse');
  await act(async () => reactProps(confirm).onClick());
  assert.deepEqual(calls, [74]);
});

test('un cancelado permite registrar una transferencia pendiente que efectivamente ingresó', async (t) => {
  const calls = [];
  const canceled = { ...order, estado: 'CANCELADO', metodo_pago_acordado: 'TRANSFERENCIA', pagos: [{ id: 75, tipo: 'COBRO', estado: 'PENDIENTE', metodo_pago: 'TRANSFERENCIA', monto: '12000' }] };
  const container = await mount(t, OrderPayments, { order: canceled, userId: 1, busy: false,
    commands: { reconcile: (id) => { calls.push(id); } }, run: async (operation) => operation() });
  const confirm = elements(container, (node) => node.localName === 'button' && node.textContent.startsWith('Confirmar ingreso de'))[0];
  assert.ok(confirm, 'Cancelar no debe ocultar un ingreso pendiente real');
  await act(async () => reactProps(confirm).onClick());
  assert.deepEqual(calls, [75]);
});

test('el cobro simplificado conserva cuerpo y UUID al perder una respuesta', async (t) => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push({ path, body: JSON.parse(options.body) });
    if (calls.length === 1) throw new Error('Respuesta perdida');
    return response({ id: 51, estado: 'CONCILIADO' });
  };
  const container = await mount(t, OrderPayments, { order, userId: 1, commands: {}, busy: false,
    run: async (operation) => { try { await operation(); } catch { /* El panel muestra el error y conserva el intento. */ } } });
  await submit(container);
  assert.match(container.textContent, /Reintentar operación guardada/);
  assert.equal(elements(container, (node) => node.localName === 'select').length, 0);
  await submit(container);
  assert.deepEqual(calls[1], calls[0]);
  assert.ok(calls[1].body.clave_operacion);
});

test('un cancelado ofrece devolver sólo lo cobrado y exige confirmar que se devolvió', async (t) => {
  const calls = [];
  globalThis.fetch = async (path, options) => { calls.push({ path, body: JSON.parse(options.body) }); return response({ id: 52, estado: 'CONCILIADO' }); };
  const container = await mount(t, OrderPayments, { order: { ...order, estado: 'CANCELADO', neto_cobrado: '500' }, userId: 1, commands: {}, busy: false, run: async (operation) => operation() });
  await submit(container);
  assert.equal(calls.length, 0);
  const confirm = button(container, 'Sí, registrar devolución');
  assert.ok(confirm);
  await act(async () => reactProps(confirm).onClick());
  assert.equal(calls[0].path, '/api/pagos/devolucion?incluir_pedido=true');
  assert.equal(calls[0].body.monto, '500');
  assert.ok(calls[0].body.motivo.trim());
});

test('actualizar el saldo después de cobrar no deja habilitado el importe anterior', async (t) => {
  let update;
  function PaymentSnapshot() {
    const [snapshot, setSnapshot] = useState(order);
    useLayoutEffect(() => { update = setSnapshot; }, [setSnapshot]);
    return createElement(OrderPayments, { order: snapshot, userId: 1, commands: {}, busy: false, run: async (operation) => operation() });
  }
  const container = await mount(t, PaymentSnapshot, {});
  assert.match(container.textContent, /Cobrar/);
  await act(async () => update({ ...order, saldo_pendiente: '0', neto_cobrado: '12000' }));
  assert.equal(elements(container, (node) => node.localName === 'button' && node.textContent.startsWith('Cobrar')).length, 0);
  assert.match(container.textContent, /Pagado/);
});

test('la acción directa no permite preparar una transferencia aún impaga', async (t) => {
  let calls = 0;
  const container = await mount(t, StateOperation, { order: { ...order, metodo_pago_acordado: 'TRANSFERENCIA' }, role: 'EMPLEADO', busy: false,
    commands: { state: () => { calls += 1; } }, run: async (operation) => operation() });
  const cook = button(container, 'Enviar a cocina');
  assert.equal(reactProps(cook).disabled, true);
  await act(async () => reactProps(cook).onClick());
  assert.equal(calls, 0);
});

test('regreso de delivery requiere confirmar el regreso real, sin escribir un motivo', async (t) => {
  let sent;
  const delivered = { ...order, estado: 'ENTREGADO', envio: { id: 7, viaje_id: 4, repartidor_id: 8, estado: 'ENTREGADO', estado_viaje: 'FINALIZADO' } };
  const container = await mount(t, OrderDelivery, { order: delivered, role: 'DUENIO', busy: false,
    commands: { trip: async () => ({ repartidor_nombre: 'Ana' }), shipment: (id, action, body) => { sent = { id, action, body }; } }, run: async (operation) => operation() });
  await submit(container);
  assert.equal(sent, undefined);
  const confirm = button(container, 'Confirmar regreso al local');
  assert.ok(confirm);
  await act(async () => reactProps(confirm).onClick());
  assert.equal(sent.id, 7);
  assert.equal(sent.action, 'corregir-entrega');
  assert.equal(sent.body.regreso_confirmado, true);
  assert.equal(sent.body.version_esperada, order.version);
  assert.ok(sent.body.motivo.trim());
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

test('comando físico protege el cierre y usa su respuesta sin bloquear por otro GET', async (t) => {
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
  await act(async () => reactProps(button(container, 'Enviar a cocina')).onClick());
  assert.equal(reactProps(button(container, 'Cerrar detalle')).disabled, true);
  await act(async () => reactProps(elements(container, (node) => node.localName === 'dialog')[0]).onCancel({ preventDefault() {} }));
  assert.equal(closed, 0);
  await act(async () => { writing.resolve(response({ ...order, estado: 'CONFIRMADO', version: 4, tipo_entrega: 'RETIRO' })); });
  assert.equal(reactProps(button(container, 'Cerrar detalle')).disabled, false);
  await act(async () => reactProps(button(container, 'Cerrar detalle')).onClick());
  assert.equal(closed, 1);
  assert.equal(detailCalls, 1);
  assert.equal(readSignal, undefined);
  await act(async () => { readingAfterWrite.resolve(response({ ...order, numero: 999 })); });
  assert.doesNotMatch(container.textContent, /Pedido #999/);
});

test('respuesta de estado habilita la siguiente acción sin esperar detalle ni tablero', async (t) => {
  const waiting = deferred();
  let details = 0;
  let writes = 0;
  globalThis.fetch = async (path, options = {}) => {
    if (path === '/api/pedidos/17') { details += 1; return details === 1 ? response(order) : waiting.promise; }
    if (options.method === 'PATCH') { writes += 1; return response({ ...order, estado: 'EN_PREPARACION', version: 4 }); }
    return waiting.promise;
  };
  const container = await mount(t, OrderDetail, { id: 17, onClose() {} }, true);
  await act(async () => reactProps(button(container, 'Enviar a cocina')).onClick());
  const ready = button(container, 'Marcar listo');
  assert.ok(ready);
  assert.equal(reactProps(ready).disabled, false);
  assert.equal(details, 1);
  assert.equal(writes, 1);
  await act(async () => { waiting.resolve(response([])); });
});

test('confirmar transferencia habilita cocina con el pedido devuelto por el cobro', async (t) => {
  const waiting = deferred();
  let details = 0;
  let payments = 0;
  const transfer = { ...order, metodo_pago_acordado: 'TRANSFERENCIA' };
  globalThis.fetch = async (path, options = {}) => {
    if (path === '/api/pedidos/17') { details += 1; return details === 1 ? response(transfer) : waiting.promise; }
    if (path.startsWith('/api/pagos/transferencia')) {
      payments += 1;
      assert.equal(JSON.parse(options.body).pedido_id, 17);
      return response({ id: 55, estado: 'CONCILIADO', pedido: { ...transfer, saldo_pendiente: '0', neto_cobrado: '12000', pagos: [{ id: 55, tipo: 'COBRO', estado: 'CONCILIADO', metodo_pago: 'TRANSFERENCIA', monto: '12000' }] } });
    }
    return waiting.promise;
  };
  const container = await mount(t, OrderDetail, { id: 17, onClose() {} }, true);
  assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, true);
  await act(async () => { void reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); });
  assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, false);
  assert.equal(payments, 1);
  assert.equal(details, 1);
  assert.match(container.textContent, /Pagado/);
  await act(async () => { waiting.resolve(response([])); });
});

test('un error no queda disfrazado de Guardando y conserva el pago registrado', async (t) => {
  const paid = { ...order, metodo_pago_acordado: 'TRANSFERENCIA', saldo_pendiente: '0', neto_cobrado: '12000' };
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'PATCH') return { ok: false, status: 500, json: async () => { throw new Error('HTML'); } };
    return response(path === '/api/pedidos/17' ? paid : []);
  };
  const container = await mount(t, OrderDetail, { id: 17, onClose() {} }, true);
  await act(async () => reactProps(button(container, 'Enviar a cocina')).onClick());
  await completed(() => container.textContent.includes('HTTP 500'));
  assert.doesNotMatch(container.textContent, /Guardando|Registrando operación/);
  assert.match(container.textContent, /Pagado/);
  assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, true);
  await act(async () => reactProps(button(container, 'Actualizar detalle')).onClick());
  assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, false);
});

test('cocina puede operar otra comanda mientras una confirma su cambio', async (t) => {
  const first = deferred();
  const second = deferred();
  const active = [17, 18].map((id) => ({ ...order, id, numero: id, estado: 'EN_PREPARACION' }));
  const writes = [];
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'PATCH') { writes.push(path); return path.includes('/17/') ? first.promise : second.promise; }
    return response(active);
  };
  let data;
  function CaptureKitchen() { const current = useData(); useLayoutEffect(() => { data = current; }); return createElement(Kitchen); }
  const container = await mount(t, CaptureKitchen, {}, true);
  const ready = elements(container, (node) => node.localName === 'button' && node.textContent === 'Listo para reparto');
  assert.equal(ready.length, 2);
  await act(async () => reactProps(ready[0]).onClick());
  assert.equal(reactProps(ready[1]).disabled, false);
  await act(async () => reactProps(ready[1]).onClick());
  assert.equal(writes.length, 2);
  await act(async () => { second.resolve(response({ ...active[1], estado: 'LISTO', version: 4 })); });
  assert.equal(data.state.orders.find((item) => item.id === 18).estado, 'LISTO');
  assert.equal(data.state.orders.find((item) => item.id === 17).estado, 'EN_PREPARACION');
  await act(async () => { first.resolve(response({ ...active[0], estado: 'LISTO', version: 4 })); });
  assert.equal(data.state.orders.length, 2);
  assert.ok(data.state.orders.every((item) => item.estado === 'LISTO'));
});
