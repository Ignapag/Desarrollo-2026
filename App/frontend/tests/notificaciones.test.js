import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createInboxResource } from '../src/notifications/inboxResource.js';
import { categoryUnreadCount, notificationCategory, inboxNotifications, stockNotifications, sortNotifications, elapsedTime, validateInbox, readNotificationKeys } from '../src/notifications/notificationModel.js';
import { createNotificationReading } from '../src/notifications/notificationReading.js';

const empty = () => ({ comprobantes: [], atenciones: [], cambios: [], salidas: [] });
const receipt = (extra = {}) => ({ id: 5, pedido_id: 125, numero: 125, estado: 'PENDIENTE', creado_en: '2026-10-28T15:00:00-03:00', ...extra });
const deferred = () => { let resolve; let reject; const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; }); return { promise, resolve, reject }; };
const memory = () => { const entries = new Map(); return { getItem: (key) => entries.get(key), setItem: (key, value) => entries.set(key, value) }; };

test('incluye sólo comprobantes, atención humana y niveles de stock confirmados por la API', () => {
  const data = { ...empty(), comprobantes: [receipt()], cambios: [{ id: 44 }], atenciones: [
    { id: 6, estado: 'PENDIENTE', motivo: 'SOLICITUD' },
    { id: 7, estado: 'PENDIENTE', motivo: 'COMPROBANTE' },
    { id: 8, estado: 'PENDIENTE', motivo: 'CAMBIO' },
    { id: 9, estado: 'PENDIENTE', motivo: 'CANCELACION' },
  ] };
  const stock = stockNotifications([
    { id: 1, name: 'Pan', level: 'SIN_STOCK' },
    { id: 2, name: 'Queso', level: 'BAJO_UMBRAL' },
    { id: 3, name: 'Carne', level: 'NORMAL', stock: 0 },
    { id: 4, name: 'Inactivo', level: 'SIN_STOCK', active: false },
    { id: 5, name: 'Sin nivel', stock: 0 },
  ]);
  const result = sortNotifications([...inboxNotifications(validateInbox(data)), ...stock]);
  assert.deepEqual(result.map((item) => item.key), ['stock:1:SIN_STOCK', 'comprobante:5', 'atencion:7', 'atencion:6', 'stock:2:BAJO_UMBRAL']);
  assert.ok(result.every((item) => item.pending));
  assert.equal(result.find((item) => item.key === 'atencion:7').href, '/dashboard/orders?bandeja=comprobantes&aviso=whatsapp-atencion-7');
  assert.equal(result[0].date, null);
});

test('Todas conserva comprobantes revisados y ordena las novedades por prioridad y fecha sin duplicados', () => {
  const items = inboxNotifications({ ...empty(), comprobantes: [receipt({ id: 1, creado_en: '2026-10-28T14:00:00-03:00' }), receipt({ id: 2 }), receipt({ id: 3, estado: 'APROBADO' })] });
  const result = sortNotifications([...items, ...items]);
  assert.equal(result.length, 3);
  assert.equal(result[0].key, 'comprobante:2');
  assert.equal(result.find((item) => item.key === 'comprobante:3').pending, false);
  assert.equal(result.find((item) => item.key === 'comprobante:3').title, 'Comprobante revisado');
});

test('la lectura no resuelve el pendiente y se aísla por usuario guardando sólo claves', () => {
  const storage = memory();
  const first = createNotificationReading(storage, 1);
  const event = inboxNotifications({ ...empty(), comprobantes: [receipt()] })[0];
  first.mark([event.key]);
  assert.equal(event.pending, true);
  assert.deepEqual(first.getSnapshot().keys, ['comprobante:5']);
  assert.deepEqual(createNotificationReading(storage, 1).getSnapshot().keys, ['comprobante:5']);
  assert.deepEqual(createNotificationReading(storage, 2).getSnapshot().keys, []);
  assert.deepEqual(readNotificationKeys({ getItem: () => '["teléfono privado", "__proto__", "stock:3:SIN_STOCK"]' }, 1), ['stock:3:SIN_STOCK']);
});

test('una recuperación de stock confirmada habilita una nueva alerta sin repetir la misma durante el faltante', () => {
  const reading = createNotificationReading(memory(), 1);
  reading.mark(['stock:1:BAJO_UMBRAL', 'comprobante:5']);
  reading.retainStock(new Set(['stock:1:BAJO_UMBRAL']));
  assert.equal(reading.getSnapshot().keys.length, 2);
  reading.retainStock(new Set());
  assert.deepEqual(reading.getSnapshot().keys, ['comprobante:5']);
});

test('almacenamiento bloqueado conserva la lectura en memoria e informa la limitación', () => {
  const reading = createNotificationReading({ getItem: () => { throw Error('Bloqueado'); }, setItem: () => { throw Error('Bloqueado'); } }, 1);
  reading.mark(['atencion:4']);
  assert.deepEqual(reading.getSnapshot().keys, ['atencion:4']);
  assert.equal(reading.getSnapshot().storageError, true);
});

test('la campanita y la bandeja comparten una consulta en curso y reutilizan su instantánea', async () => {
  const waiting = deferred(); let calls = 0;
  const resource = createInboxResource(() => { calls += 1; return waiting.promise; }, validateInbox);
  const first = resource.load(); const second = resource.load(true);
  assert.equal(first, second);
  waiting.resolve(empty()); await first;
  await resource.load();
  assert.equal(calls, 1);
});

test('un error conserva datos anteriores y el reintento recupera; un 403 retira datos privados', async () => {
  let failure;
  const resource = createInboxResource(async () => { if (failure) throw failure; return { ...empty(), comprobantes: [receipt()] }; }, validateInbox);
  await resource.load();
  failure = Error('Sin red'); await assert.rejects(resource.load(true));
  assert.equal(resource.getSnapshot().data.comprobantes.length, 1);
  assert.equal(resource.getSnapshot().error, true);
  failure = null; await resource.load(true); assert.equal(resource.getSnapshot().error, false);
  failure = Object.assign(Error('Prohibido'), { status: 403 }); await assert.rejects(resource.load(true));
  assert.equal(resource.getSnapshot().data, null);
});

test('descarta una consulta anterior a la revisión y una respuesta tardía de otra sesión', async () => {
  const old = deferred(); let calls = 0;
  const resource = createInboxResource(() => ++calls === 1 ? old.promise : Promise.resolve(empty()), validateInbox);
  const previous = resource.load(); await Promise.resolve();
  resource.cancel(); await resource.load(true);
  old.resolve({ ...empty(), comprobantes: [receipt()] }); await previous;
  assert.equal(resource.getSnapshot().data.comprobantes.length, 0);
  const another = createInboxResource(async () => empty(), validateInbox);
  assert.equal(another.getSnapshot().data, null);
});

test('datos inválidos no se convierten en un vacío exitoso ni exponen el cuerpo recibido', async () => {
  const resource = createInboxResource(async () => ({ detail: 'datos privados' }), validateInbox);
  await assert.rejects(resource.load());
  assert.equal(resource.getSnapshot().data, null);
  assert.equal(resource.getSnapshot().error, true);
  assert.equal(JSON.stringify(resource.getSnapshot()).includes('datos privados'), false);
});

test('el tiempo usa sólo fechas existentes y tolera fechas inválidas', () => {
  const now = Date.parse('2026-10-28T15:05:00-03:00');
  assert.equal(elapsedTime('2026-10-28T15:00:00-03:00', now), 'Hace 5 minutos');
  assert.equal(elapsedTime(null, now), null);
  assert.equal(elapsedTime('inválida', now), null);
});


test('STOCK y CLIENTES separan clases y sus contadores suman el global sin marcar lectura', () => {
  const items = [
    { key: 'stock:1:SIN_STOCK', kind: 'stock', read: false },
    { key: 'comprobante:2', kind: 'comprobante', read: false },
    { key: 'atencion:3', kind: 'atencion', read: true },
  ];
  assert.equal(notificationCategory(items[0]), 'stock');
  assert.equal(notificationCategory(items[1]), 'clientes');
  assert.equal(notificationCategory(items[2]), 'clientes');
  assert.equal(categoryUnreadCount(items, 'stock'), 1);
  assert.equal(categoryUnreadCount(items, 'clientes'), 1);
  assert.equal(items[0].read, false);
});
