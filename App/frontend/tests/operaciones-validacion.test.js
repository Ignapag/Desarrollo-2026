import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps } from './minimal-dom.js';
import { createPaymentAttempt, executePayment } from '../src/fulfillment/orderCommands.js';
import { paymentFixture } from './payment-fixtures.js';

let server, dom, createRoot, OrderPayments, EditOperation, OrderDelivery, OrderDetail, store;
const originalFetch = globalThis.fetch;
const order = { id: 481, numero: 48, version: 1, estado: 'PENDIENTE', tipo_entrega: 'DELIVERY', direccion_id: 1, metodo_pago_acordado: 'EFECTIVO', direccion: { calle: 'Calle', numero: '10', localidad: 'Ensenada' }, saldo_pendiente: '1000', neto_cobrado: '100', total: '1000', items: [], pagos: [], historial: [] };
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'operation-validation-context', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return `export const user = { id: 1, backendRole: 'EMPLEADO', permisos: ['pedidos.ver', 'pedidos.editar'] }; export const useAuth = () => ({user});`;
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return `export const operations=[]; export const useData=()=>({ state:{orders:[]},orderOperationPending:()=>false,startOrderOperation:(value)=>{operations.push(value); return true;} });`;
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: OrderPayments } = await server.ssrLoadModule('/src/fulfillment/OrderPayments.jsx'));
  ({ EditOperation } = await server.ssrLoadModule('/src/fulfillment/OrderOperationForms.jsx'));
  ({ default: OrderDelivery } = await server.ssrLoadModule('/src/fulfillment/OrderDelivery.jsx'));
  ({ default: OrderDetail } = await server.ssrLoadModule('/src/fulfillment/OrderDetail.jsx'));
  store = await server.ssrLoadModule('/src/shared/store/DataContext.jsx');
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });
async function mount(t, Component, props) {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(Component, props)));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
const field = (container, label) => elements(elements(container, (node) => node.localName === 'label' && node.firstChild?.textContent === label)[0], (node) => ['input', 'textarea', 'select'].includes(node.localName))[0];
const change = (node, value) => act(async () => reactProps(node).onChange({ target: { value } }));
const submit = (container) => act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
const response = (data) => ({ ok: true, status: 200, json: async () => data });

test('un importe con más de dos decimales no crea un intento financiero', async (t) => {
  let operations = 0;
  const container = await mount(t, OrderPayments, { order, userId: 1, commands: {}, busy: false, run: async () => { operations += 1; } });
  await change(field(container, 'Importe a cobrar'), '12.345');
  await submit(container);
  assert.equal(operations, 0);
  assert.match(container.textContent, /dos decimales|2 decimales/);
});

test('el cobro admite coma decimal y envía el importe canónico al servidor', async (t) => {
  let sent;
  globalThis.fetch = async (_url, options) => { sent = JSON.parse(options.body); return response(paymentFixture({ id: 901, orderId: 482, amount: '12.50' })); };
  const container = await mount(t, OrderPayments, { order: { ...order, id: 482 }, userId: 1, commands: {}, busy: false, run: async (operation) => operation() });
  await change(field(container, 'Importe a cobrar'), '12,50');
  assert.doesNotMatch(container.textContent, /No disponible/);
  await submit(container);
  assert.equal(sent?.monto_a_pagar, '12.50');
});

test('un motivo corto de devolución se corrige antes de fijar cuerpo y UUID', async (t) => {
  let operations = 0;
  const container = await mount(t, OrderPayments, { order: { ...order, id: 483, estado: 'CANCELADO' }, userId: 1, commands: {}, busy: false, run: async () => { operations += 1; } });
  await change(field(container, 'Nota (opcional)'), 'ok');
  await submit(container);
  const confirm = elements(container, (node) => node.localName === 'button' && node.textContent === 'Sí, registrar devolución')[0];
  if (confirm) await act(async () => reactProps(confirm).onClick());
  assert.equal(operations, 0);
  assert.match(container.textContent, /3 caracteres|tres caracteres/);
});

test('la dirección con espacios conserva la edición y señala el campo inválido', async (t) => {
  let operations = 0;
  const container = await mount(t, EditOperation, { order, role: 'EMPLEADO', commands: {}, busy: false, run: () => { operations += 1; } });
  await change(field(container, 'Calle'), '   ');
  await submit(container);
  assert.equal(operations, 0);
  assert.equal(reactProps(field(container, 'Calle'))['aria-invalid'], true);
  assert.match(container.textContent, /Completá|Ingresá/);
});

test('editar desde el detalle no cierra el formulario antes de guardar', async (t) => {
  let closed = 0;
  store.operations.length = 0;
  globalThis.fetch = async () => response(order);
  const container = await mount(t, OrderDetail, { id: order.id, onClose: () => { closed += 1; } });
  await change(field(container, 'Observaciones'), 'Conservar si falla');
  await submit(container);
  assert.equal(store.operations.length, 1);
  assert.equal(closed, 0);
  assert.equal(typeof store.operations[0].onError, 'function');
  await act(async () => store.operations[0].onError('No se guardó.'));
  assert.equal(reactProps(field(container, 'Observaciones')).value, 'Conservar si falla');
});

test('un conflicto seguido de recarga conserva el borrador y exige rebase explícito a la nueva versión', async (t) => {
  store.operations.length = 0;
  let current = { ...order, observaciones: 'Original' };
  globalThis.fetch = async () => response(current);
  const container = await mount(t, OrderDetail, { id: order.id, onClose() {} });
  await change(field(container, 'Observaciones'), 'Mi borrador pendiente');
  await submit(container);
  await act(async () => store.operations[0].onError('Conflicto HTTP 409'));
  current = { ...current, version: 2, observaciones: 'Cambio de otra persona', metodo_pago_acordado: 'TRANSFERENCIA' };
  const update = elements(container, (node) => node.localName === 'button' && node.textContent === 'Actualizar detalle')[0];
  await act(async () => reactProps(update).onClick());
  assert.equal(reactProps(field(container, 'Observaciones')).value, 'Mi borrador pendiente');
  await submit(container);
  assert.equal(store.operations.length, 1, 'No debe reenviar sobre una versión nueva sin revisar');
  const rebase = elements(container, (node) => node.localName === 'button' && node.textContent === 'Conservar borrador sobre la versión actual')[0];
  assert.ok(rebase);
  await act(async () => reactProps(rebase).onClick());
  assert.equal(reactProps(field(container, 'Método de pago acordado')).value, 'TRANSFERENCIA', 'Adopta campos que el operador no cambió');
  await submit(container);
  let sent;
  globalThis.fetch = async (_url, options) => { sent = JSON.parse(options.body); return response(current); };
  await store.operations[1].operation();
  assert.equal(sent.version_esperada, 2);
  assert.equal(sent.observaciones, 'Mi borrador pendiente');
  assert.equal(Object.hasOwn(sent, 'metodo_pago_acordado'), false);
  await act(async () => store.operations[1].onSuccess({ ...current, version: 3, observaciones: 'Mi borrador pendiente' }));
  assert.equal(reactProps(field(container, 'Observaciones')).value, 'Mi borrador pendiente');
  assert.doesNotMatch(container.textContent, /Conservar borrador sobre la versión actual/);
});

test('un detalle HTTP 200 incompleto muestra un error recuperable y no rompe el render', async (t) => {
  globalThis.fetch = async () => response({});
  const container = await mount(t, OrderDetail, { id: order.id, onClose() {} });
  assert.match(container.textContent, /No se pudo verificar el detalle/);
  assert.ok(elements(container, (node) => node.localName === 'button' && node.textContent === 'Actualizar detalle')[0]);
  assert.equal(elements(container, (node) => node.localName === 'form').length, 0);
});

test('el detalle de reparto no consulta viajes sin permiso de lectura', async (t) => {
  let calls = 0;
  await mount(t, OrderDelivery, { order: { ...order, estado: 'EN_CAMINO', envio: { viaje_id: 20, estado: 'EN_CAMINO', estado_viaje: 'EN_RUTA', repartidor_id: 2 } }, busy: false, can: (permission) => permission === 'delivery.operar', commands: { trip: async () => { calls += 1; return {}; } } });
  assert.equal(calls, 0);
});

test('un pago sin identificador verificable no anuncia un resultado guardado', async () => {
  const attempt = createPaymentAttempt({ pedido_id: 1, monto: '100' }, 'devolucion', () => 'test-operation');
  await assert.rejects(executePayment(async () => ({}), attempt), /confirmar|verificar/);
});

for (const kind of ['efectivo', 'devolucion']) {
  test(`un acuse incompleto de ${kind} conserva cuerpo y UUID para reintentar`, async (t) => {
    const calls = [];
    globalThis.fetch = async (_url, options) => { calls.push(JSON.parse(options.body)); return response({ id: 901 }); };
    const container = await mount(t, OrderPayments, { order: { ...order, id: kind === 'efectivo' ? 485 : 486, estado: kind === 'efectivo' ? 'PENDIENTE' : 'CANCELADO' }, userId: 1, commands: {}, busy: false, run: async (operation) => { try { await operation(); } catch { /* El detalle mantiene el error y el intento. */ } } });
    await submit(container);
    if (kind === 'devolucion') await act(async () => reactProps(elements(container, (node) => node.localName === 'button' && node.textContent === 'Sí, registrar devolución')[0]).onClick());
    assert.match(container.textContent, /Reintentar operación guardada/);
    await submit(container);
    assert.deepEqual(calls[1], calls[0]);
    assert.ok(calls[0].clave_operacion);
  });
}

for (const [label, mutate] of [
  ['estado ausente', (value) => { delete value.estado; }],
  ['pedido diferente', (value) => { value.pedido_id = 99; }],
  ['monto diferente', (value) => { value.monto = '101'; }],
  ['tipo incorrecto', (value) => { value.tipo = 'COBRO'; }],
  ['método diferente', (value) => { value.metodo_pago = 'TRANSFERENCIA'; }],
]) {
  test(`la devolución con ${label} no confirma ni libera el intento`, async () => {
    const attempt = createPaymentAttempt({ pedido_id: 1, monto: '100', metodo_pago: 'EFECTIVO' }, 'devolucion', () => 'retained-operation');
    const receipt = paymentFixture({ kind: 'devolucion', orderId: 1, amount: '100' });
    mutate(receipt);
    await assert.rejects(executePayment(async () => receipt, attempt), /confirmar/);
    assert.equal(attempt.body.clave_operacion, 'retained-operation');
  });
}

test('una conciliación sin identificador conserva el reintento de la transferencia', async () => {
  const attempt = createPaymentAttempt({ pedido_id: 1, monto: '100' }, 'transferencia', () => 'test-transfer');
  let requests = 0;
  await assert.rejects(executePayment(async () => ++requests === 1 ? paymentFixture({ kind: 'transferencia', id: 99, orderId: 1, amount: '100', state: 'PENDIENTE' }) : {}, attempt), /quedó registrada/);
});

test('un repartidor retirado de la disponibilidad no se envía por una selección vieja', async (t) => {
  let reads = 0;
  let writes = 0;
  const container = await mount(t, OrderDelivery, { order: { ...order, estado: 'LISTO' }, busy: false, can: (permission) => permission === 'delivery.planificar', run: () => { writes += 1; }, commands: { riders: async () => ++reads === 1 ? [{ id: 2, nombre: 'Rider' }] : [] } });
  await change(field(container, 'Repartidor disponible'), '2');
  const refresh = elements(container, (node) => node.localName === 'button' && node.textContent === 'Consultar disponibilidad nuevamente')[0];
  await act(async () => reactProps(refresh).onClick());
  await submit(container);
  assert.equal(writes, 0);
});
