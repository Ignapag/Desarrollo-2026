import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ORDER_STATES, mapOrder, ordersPath, stateCommands, hasAssignment, canEditOperation, createFreshnessFence, ageMinutes, money } from '../src/fulfillment/orderModel.js';
import { createOrderCommands, createPaymentAttempt, executePayment } from '../src/fulfillment/orderCommands.js';
import { paymentFixture } from './payment-fixtures.js';

const base = { id: 999, numero: 12, estado: 'PENDIENTE', version: 6, tipo_entrega: 'DELIVERY', cliente: 'Ana', total: '12000', saldo_pendiente: '2000', neto_cobrado: '10000', items: [{ id: 1, cantidad: 2, nombre_producto: 'Monu', aclaraciones: 'Sin sal' }], creado_en: '2026-10-17T16:00:00Z', telefono: '5492211234567', direccion: { calle: 'Camino', numero: '123', localidad: 'Ensenada' }, pagos: [], historial: [] };
const commandsFor = (order, role = 'EMPLEADO') => stateCommands(order, role);

test('el modelo conserva número público, contacto, saldo, versión y detalle real', () => {
  const order = mapOrder(base);
  assert.equal(order.id, 999);
  assert.equal(order.number, 12);
  assert.equal(order.phone, base.telefono);
  assert.equal(order.address, 'Camino, 123, Ensenada');
  assert.equal(order.version, 6);
  assert.equal(order.neto_cobrado, '10000');
  assert.deepEqual(order.items, ['2x Monu · Sin sal']);
  assert.equal(mapOrder({ ...base, tipo_entrega: 'RETIRO' }).address, 'Retiro en local');
});

test('todos los estados, incluidos confirmado y cerrados, tienen una columna', () => {
  assert.deepEqual(ORDER_STATES.map(([id]) => id), ['PENDIENTE', 'CONFIRMADO', 'EN_PREPARACION', 'LISTO', 'EN_CAMINO', 'ENTREGADO', 'CANCELADO']);
});

test('la búsqueda e historial se filtran en la API sin imponer un límite local', () => {
  assert.equal(ordersPath({ q: ' 12 Ana ', activos: false }), '/api/pedidos?q=12+Ana&activos=false');
  assert.equal(ordersPath({ estado: 'CONFIRMADO', activos: true }), '/api/pedidos?estado=CONFIRMADO&activos=true');
  assert.equal(ordersPath(), '/api/pedidos');
});

test('un viaje histórico finalizado no bloquea editar una compra recuperada', () => {
  const order = { ...base, estado: 'LISTO', envio: { viaje_id: 2, repartidor_id: 8, estado: 'ENTREGADO', estado_viaje: 'FINALIZADO' } };
  assert.equal(hasAssignment(order), false);
  assert.equal(canEditOperation(order, 'EMPLEADO'), true);
});

test('una entrega delivery errónea vuelve a listo por el comando de regreso real', () => {
  const order = { ...base, estado: 'ENTREGADO', envio: { viaje_id: 2, repartidor_id: 8, estado: 'ENTREGADO', estado_viaje: 'FINALIZADO' } };
  assert.ok(!commandsFor(order, 'DUENIO').some((command) => command.estado === 'LISTO'));
});

test('un fallo en ruta mantiene la asignación y bloquea edición/correcciones directas', () => {
  const order = { ...base, estado: 'EN_CAMINO', envio: { viaje_id: 2, repartidor_id: 8, estado: 'FALLIDO', estado_viaje: 'EN_RUTA' } };
  assert.equal(hasAssignment(order), true);
  assert.equal(canEditOperation(order, 'DUENIO'), false);
  assert.deepEqual(commandsFor(order, 'DUENIO'), []);
});

test('repartidor y cliente no reciben comandos de estado, edición ni pagos locales', () => {
  for (const role of ['REPARTIDOR', 'CLIENTE']) {
    assert.deepEqual(commandsFor(base, role), []);
    assert.equal(canEditOperation(base, role), false);
  }
});

test('retiro listo puede entregarse; delivery nunca salta el viaje', () => {
  const ready = { ...base, estado: 'LISTO' };
  assert.ok(commandsFor({ ...ready, tipo_entrega: 'RETIRO' }).some((command) => command.estado === 'ENTREGADO'));
  assert.ok(!commandsFor(ready).some((command) => ['EN_CAMINO', 'ENTREGADO'].includes(command.estado)));
});

test('cancelar tras cocina declara merma incluso después de corregir a pendiente', () => {
  const cooked = commandsFor({ ...base, preparacion_en: base.creado_en }).find((command) => command.estado === 'CANCELADO');
  assert.equal(cooked.tratamiento_stock, 'MERMA');
  assert.equal(cooked.correccion, true);
  assert.equal(commandsFor(base).find((command) => command.estado === 'CANCELADO').tratamiento_stock, undefined);
});

test('corregir clic de cocina conserva consumo; reapertura exige privilegio y nuevo consumo', () => {
  const cooking = commandsFor({ ...base, estado: 'EN_PREPARACION' });
  for (const destination of ['PENDIENTE', 'CONFIRMADO']) {
    const command = cooking.find(({ estado }) => estado === destination);
    assert.equal(command.correccion, true);
    assert.equal(command.tratamiento_stock, 'CONSERVAR');
  }
  const closed = { ...base, estado: 'CANCELADO' };
  assert.deepEqual(commandsFor(closed), []);
  assert.equal(commandsFor(closed, 'DUENIO')[0].tratamiento_stock, 'RECONSUMIR');
});

test('edad usa fechas reales y los importes desconocidos no se muestran como cero', () => {
  assert.equal(ageMinutes(base.creado_en, Date.parse('2026-10-17T16:07:59Z')), 7);
  assert.equal(ageMinutes(null), null);
  assert.equal(money(undefined), 'No disponible');
});

test('un GET atrasado no pisa una mutación, incluso cuando termina después del refresco', async () => {
  const fence = createFreshnessFence();
  let release;
  const oldToken = fence.read();
  const oldGet = new Promise((resolve) => { release = resolve; }).then(() => fence.accepts(oldToken));
  fence.beginMutation();
  const during = fence.read();
  fence.endMutation();
  const latest = fence.read();
  release();
  assert.equal(await oldGet, false);
  assert.equal(fence.accepts(during), false);
  assert.equal(fence.accepts(latest), true);
});

test('mutaciones simultáneas y cambio de sesión invalidan lecturas anteriores', () => {
  const fence = createFreshnessFence();
  fence.beginMutation(); fence.beginMutation(); fence.endMutation();
  const token = fence.read();
  assert.equal(fence.accepts(token), false);
  fence.endMutation();
  const newToken = fence.read();
  assert.equal(fence.accepts(newToken), true);
  fence.invalidate();
  assert.equal(fence.accepts(newToken), false);
});

test('entre dos consultas la última respuesta es la única aceptable', () => {
  const fence = createFreshnessFence();
  const first = fence.read();
  const second = fence.read();
  assert.equal(fence.accepts(first), false);
  assert.equal(fence.accepts(second), true);
});

function recorder() {
  const calls = [];
  const http = async (path, options) => { calls.push({ path, ...options, body: options?.body ? JSON.parse(options.body) : undefined }); return { id: 1 }; };
  return { calls, http, commands: createOrderCommands(http) };
}

test('el estado manda versión, origen esperado y tratamiento sin actor ni campos de UI', async () => {
  const { calls, commands } = recorder();
  await commands.state(base, { estado: 'CANCELADO', label: 'No enviar', correccion: true, tratamiento_stock: 'MERMA' }, 'Cliente canceló');
  assert.deepEqual(calls[0], { path: '/api/pedidos/999/estado', method: 'PATCH', body: { estado: 'CANCELADO', motivo: 'Cliente canceló', version_esperada: 6, estado_esperado: 'PENDIENTE', correccion: true, tratamiento_stock: 'MERMA' } });
});

test('editar y asignar operan sobre el mismo ID mediante endpoints diferentes', async () => {
  const { calls, commands } = recorder();
  await commands.edit(base, { tipo_entrega: 'RETIRO', metodo_pago_acordado: 'EFECTIVO' }, 'Cliente retira');
  await commands.assign(base.id, 8, 'Repartidor disponible');
  assert.equal(calls[0].path, '/api/pedidos/999/operacion');
  assert.equal(calls[0].body.version_esperada, 6);
  assert.deepEqual(calls[1], { path: '/api/delivery/pedidos/999/asignar', method: 'POST', body: { repartidor_id: 8, motivo: 'Repartidor disponible' } });
});

test('salida y entrega persisten por viaje y envío, sin PATCH de estado ficticio', async () => {
  const { calls, commands } = recorder();
  await commands.startTrip(4);
  await commands.shipment(7, 'entregar');
  await commands.financial(base.id);
  assert.deepEqual(calls.map(({ path }) => path), ['/api/delivery/viajes/4/iniciar', '/api/delivery/envios/7/entregar', '/api/pagos/pedido/999/estado']);
});

test('si se pierde una respuesta de efectivo el reintento conserva UUID y contenido', async () => {
  const calls = [];
  const attempt = createPaymentAttempt({ pedido_id: 999, monto_recibido: '2000', monto_a_pagar: '2000', conciliar_inmediato: true }, 'efectivo', () => 'one-operation');
  const http = async (path, options) => { calls.push({ path, body: options.body }); if (calls.length === 1) throw new Error('Conexión interrumpida'); return paymentFixture({ orderId: 999, amount: '2000' }); };
  await assert.rejects(executePayment(http, attempt), /Conexión/);
  await executePayment(http, attempt);
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(JSON.parse(calls[1].body).clave_operacion, 'one-operation');
  assert.ok(calls.every(({ path }) => path === '/api/pagos/efectivo'));
});

test('fallo parcial de transferencia reintenta el mismo registro y concilia el mismo pago', async () => {
  const calls = [];
  let failReconciliation = true;
  const http = async (path, options) => {
    calls.push({ path, body: JSON.parse(options.body) });
    if (path === '/api/pagos/transferencia') return paymentFixture({ kind: 'transferencia', orderId: 999, amount: '2000', state: 'PENDIENTE' });
    if (failReconciliation) { failReconciliation = false; throw new Error('No disponible'); }
    return paymentFixture({ kind: 'transferencia', orderId: 999, amount: '2000' });
  };
  const attempt = createPaymentAttempt({ pedido_id: 999, monto: '2000' }, 'transferencia', () => 'same-transfer');
  await assert.rejects(executePayment(http, attempt), /quedó registrada/);
  const result = await executePayment(http, attempt);
  assert.equal(result.estado, 'CONCILIADO');
  assert.deepEqual(calls[0], calls[2]);
  assert.equal(calls[1].path, '/api/pagos/51/conciliar');
  assert.equal(calls[3].path, '/api/pagos/51/conciliar');
});

test('una transferencia ya conciliada por otra vía no vuelve a conciliarse', async () => {
  const calls = [];
  const attempt = createPaymentAttempt({ pedido_id: 999, monto: '2000' }, 'transferencia', () => 'same-transfer');
  await executePayment(async (path) => { calls.push(path); return paymentFixture({ kind: 'transferencia', orderId: 999, amount: '2000' }); }, attempt);
  assert.deepEqual(calls, ['/api/pagos/transferencia']);
});

test('devolución usa movimiento separado con método, motivo y clave nueva', async () => {
  const { calls, http } = recorder();
  await executePayment(async (path, options) => { await http(path, options); return paymentFixture({ kind: 'devolucion', orderId: 999, amount: '400' }); }, createPaymentAttempt({ pedido_id: 999, monto: '400', metodo_pago: 'EFECTIVO', motivo: 'Diferencia de envío' }, 'devolucion', () => 'refund-key'));
  assert.deepEqual(calls[0].body, { pedido_id: 999, monto: '400', metodo_pago: 'EFECTIVO', motivo: 'Diferencia de envío', clave_operacion: 'refund-key' });
  assert.equal(calls[0].path, '/api/pagos/devolucion');
});
