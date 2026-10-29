import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps } from './minimal-dom.js';

let dom, server, createRoot, Orders, board, model, data;
const originalFetch = globalThis.fetch;
const minutes = (value) => new Date(Date.now() - value * 60000).toISOString();
const response = (value, status = 200) => ({ ok: status < 400, status, json: async () => value });
const raw = (id, estado, extra = {}) => ({ id, numero: id, version: 1, estado, tipo_entrega: 'RETIRO', cliente: `Cliente ${id}`, direccion: null, metodo_pago_acordado: 'EFECTIVO', total: '1000', saldo_pendiente: '1000', neto_cobrado: '0', creado_en: minutes(5), items: [{ id: id * 10, cantidad: 2, nombre_producto: 'Clásica' }], pagos: [], historial: [], ...extra });

before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'tablero-context', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "const user={id:1,backendRole:'EMPLEADO',permisos:['pedidos.ver']}; export const useAuth=()=>({user,refreshSession:async()=>{}});";
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return "export const data={state:{orders:[],ordersStatus:'ready',ordersError:null},pending:new Set(),refreshes:0}; export const useData=()=>({state:data.state,watchOrders(){},refreshOrders:async()=>{data.refreshes+=1;},orderOperationPending:(id)=>data.pending.has(id),projectOrder:(order)=>order,startOrderOperation:()=>false});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Orders } = await server.ssrLoadModule('/src/fulfillment/Orders.jsx'));
  board = await server.ssrLoadModule('/src/fulfillment/orderBoard.js');
  model = await server.ssrLoadModule('/src/fulfillment/orderModel.js');
  ({ data } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });

function useOrders(list) {
  data.state = { orders: list.map(model.mapOrder), ordersStatus: 'ready', ordersError: null };
  data.pending = new Set();
}
async function mount(t, entry = '/dashboard/orders') {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(MemoryRouter, { initialEntries: [entry] }, createElement(Orders))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  container.rerender = () => act(async () => root.render(createElement(MemoryRouter, { initialEntries: [entry] }, createElement(Orders))));
  return container;
}
const buttons = (container) => elements(container, (node) => node.localName === 'button');
const statusButton = (container, label) => buttons(container).find((node) => node.getAttribute('aria-label')?.startsWith(`${label}:`));
const opener = (container, number) => buttons(container).find((node) => node.textContent === `Abrir pedido #${number}`);
const sections = (container) => elements(container, (node) => node.localName === 'section' && node.getAttribute('aria-labelledby')?.startsWith('orders-state-'));
const cardNumbers = (section) => elements(section, (node) => node.localName === 'button').map((node) => node.textContent);
const settle = () => act(async () => new Promise((resolve) => setTimeout(resolve, 300)));

test('el tablero conserva repartos asignados, en camino y entregados históricos por cobrar', async (t) => {
  useOrders([
    raw(701, 'LISTO', { tipo_entrega: 'DELIVERY', envio: { viaje_id: 5, repartidor_id: 3, estado: 'ASIGNADO', estado_viaje: 'PLANIFICADO' } }),
    raw(702, 'EN_CAMINO', { tipo_entrega: 'DELIVERY', envio: { viaje_id: 6, repartidor_id: 3, estado: 'EN_CAMINO', estado_viaje: 'EN_RUTA' } }),
    raw(703, 'ENTREGADO'),
  ]);
  const container = await mount(t);
  assert.equal(Boolean(opener(container, 701)), true);
  assert.equal(Boolean(opener(container, 702)), true);
  assert.equal(Boolean(opener(container, 703)), true);
  assert.equal(Boolean(statusButton(container, 'Por cobrar')), true);
  const groups = board.groupOrders(data.state.orders, board.scopeStates('active'), Date.now());
  assert.deepEqual(groups.POR_COBRAR.orders.map((o) => o.id), [703]);
  assert.equal(groups.EN_CAMINO.count, 1);
});

test('ordena operativos por espera y cerrados por cierre más reciente', () => {
  const ordered = board.sortOrders([raw(1, 'PENDIENTE', { creado_en: minutes(3) }), raw(2, 'PENDIENTE', { creado_en: minutes(40) }), raw(3, 'PENDIENTE', { creado_en: null })].map(model.mapOrder), 'PENDIENTE');
  assert.deepEqual(ordered.map((order) => order.id), [2, 1, 3]);
  const closed = board.sortOrders([raw(4, 'ENTREGADO', { entregado_en: minutes(90) }), raw(5, 'ENTREGADO', { entregado_en: minutes(2) })].map(model.mapOrder), 'ENTREGADO');
  assert.deepEqual(closed.map((order) => order.id), [5, 4]);
  assert.equal(board.formatWait(75), '1 h 15 min');
});

test('alertas de transferencia, saldo al cerrar y espera alta', () => {
  const now = Date.now();
  const labels = (order, pending) => board.orderAlerts(model.mapOrder(order), { now, pending }).map((alert) => alert.label);
  assert.deepEqual(labels(raw(1, 'PENDIENTE', { metodo_pago_acordado: 'TRANSFERENCIA', creado_en: minutes(45) }), true), ['Operación en curso', 'Espera transferencia', 'Espera alta']);
  assert.deepEqual(labels(raw(5, 'EN_PREPARACION', { metodo_pago_acordado: 'TRANSFERENCIA' })), []);
  assert.deepEqual(labels(raw(2, 'CONFIRMADO', { saldo_pendiente: '0', pagos: [{ tipo: 'COBRO', estado: 'PENDIENTE', metodo_pago: 'TRANSFERENCIA' }] })), ['Transferencia por revisar']);
  assert.deepEqual(labels(raw(3, 'ENTREGADO', { creado_en: minutes(300) })), ['Entregado con saldo']);
  assert.deepEqual(labels(raw(4, 'CANCELADO', { saldo_pendiente: '0', neto_cobrado: '500' })), ['Cobro a devolver']);
});

test('50 pedidos: conteos por estado, columnas y tarjetas compactas', async (t) => {
  const states = ['PENDIENTE', 'CONFIRMADO', 'EN_PREPARACION', 'LISTO', 'EN_CAMINO'];
  useOrders(Array.from({ length: 50 }, (_, index) => raw(index + 1, states[index % 5], { creado_en: minutes(index + 1), ...(states[index % 5] === 'CONFIRMADO' ? { neto_cobrado: '1000', saldo_pendiente: '0' } : {}) })));
  const container = await mount(t);
  assert.equal(statusButton(container, 'Todos').getAttribute('aria-label'), 'Todos: 50 pedidos, 21 con 30 minutos o más de espera');
  assert.equal(statusButton(container, 'Nuevos').getAttribute('aria-label'), 'Nuevos: 10 pedidos, 4 con 30 minutos o más de espera');
  assert.equal(reactProps(statusButton(container, 'Todos'))['aria-pressed'], true);
  const columns = sections(container);
  assert.deepEqual(columns.map((section) => section.textContent.match(/^[^,]+/)[0]), ['Nuevos', 'Pagados', 'En preparación', 'Listos', 'En camino']);
  for (const section of columns) assert.equal(cardNumbers(section).length, 10);
  assert.deepEqual(cardNumbers(columns[0]).slice(0, 3), ['Abrir pedido #46', 'Abrir pedido #41', 'Abrir pedido #36']);
  const card = elements(container, (node) => node.localName === 'article' && node.getAttribute('aria-labelledby') === 'order-card-46')[0];
  assert.match(card.textContent, /Cliente 46/);
  assert.match(card.textContent, /Retiro en local/);
  assert.match(card.textContent, /2 productos/);
  assert.doesNotMatch(card.textContent, /2x Clásica/, 'en columnas los ítems quedan para el detalle');
  assert.match(card.textContent, /Total/);
  assert.match(card.textContent, /Saldo/);
  assert.match(card.textContent, /46 min/);
  assert.match(card.textContent, /espera alta/);
});

test('enfocar un estado muestra sólo su lista y Todos vuelve al tablero', async (t) => {
  useOrders([raw(1, 'PENDIENTE'), raw(2, 'LISTO'), raw(3, 'LISTO', { creado_en: minutes(50) })]);
  const container = await mount(t);
  await act(async () => reactProps(statusButton(container, 'Listos')).onClick());
  assert.equal(reactProps(statusButton(container, 'Listos'))['aria-pressed'], true);
  assert.equal(sections(container).length, 1);
  assert.deepEqual(cardNumbers(sections(container)[0]), ['Abrir pedido #3', 'Abrir pedido #2']);
  assert.match(sections(container)[0].textContent, /2 productos · 2x Clásica/);
  await act(async () => reactProps(statusButton(container, 'Todos')).onClick());
  assert.equal(sections(container).length, 5);
});

test('en pantallas angostas se ve un estado por vez, empezando por el primero con pedidos', async (t) => {
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  t.after(() => { delete window.matchMedia; });
  useOrders([raw(1, 'EN_PREPARACION'), raw(2, 'LISTO')]);
  const container = await mount(t);
  assert.equal(statusButton(container, 'Todos'), undefined);
  assert.equal(statusButton(container, 'Nuevos').getAttribute('aria-label'), 'Nuevos: 0 pedidos');
  assert.equal(reactProps(statusButton(container, 'En preparación'))['aria-pressed'], true);
  assert.equal(sections(container).length, 1);
  await act(async () => reactProps(statusButton(container, 'Nuevos')).onClick());
  assert.match(sections(container)[0].textContent, /Sin pedidos en este estado/);
});

test('abrir el detalle y cerrarlo devuelve el foco a la tarjeta o al estado elegido', async (t) => {
  const order = raw(7, 'PENDIENTE');
  globalThis.fetch = async () => response(order);
  useOrders([order, raw(8, 'PENDIENTE')]);
  const container = await mount(t);
  await act(async () => reactProps(opener(container, 7)).onClick());
  const dialog = elements(container, (node) => node.localName === 'dialog')[0];
  assert.equal(dialog.open, true);
  assert.match(dialog.textContent, /Pedido #7/);
  await act(async () => reactProps(buttons(dialog).find((node) => node.textContent === 'Cerrar detalle')).onClick());
  assert.equal(elements(container, (node) => node.localName === 'dialog').length, 0);
  assert.equal(document.activeElement, opener(container, 7));
  await act(async () => reactProps(opener(container, 8)).onClick());
  data.pending.add(8);
  const second = elements(container, (node) => node.localName === 'dialog')[0];
  await act(async () => reactProps(buttons(second).find((node) => node.textContent === 'Cerrar detalle')).onClick());
  assert.equal(document.activeElement, opener(container, 8), 'una tarjeta que opera sigue enfocable');
  assert.equal(opener(container, 8).getAttribute('aria-disabled'), 'true');
  await act(async () => reactProps(opener(container, 8)).onClick());
  assert.equal(elements(container, (node) => node.localName === 'dialog').length, 0, 'no abre mientras opera');
  await act(async () => reactProps(opener(container, 7)).onClick());
  data.state = { ...data.state, orders: data.state.orders.filter((order) => order.id !== 7) };
  const third = elements(container, (node) => node.localName === 'dialog')[0];
  await act(async () => reactProps(buttons(third).find((node) => node.textContent === 'Cerrar detalle')).onClick());
  assert.equal(document.activeElement, statusButton(container, 'Todos'), 'sin tarjeta, vuelve al estado elegido');
});

test('el refresco periódico de búsquedas conserva el detalle abierto y el estado enfocado', async (t) => {
  const order = raw(9, 'LISTO', { cliente: 'Ana' });
  const calls = [];
  globalThis.fetch = async (path) => { calls.push(path); return response(path === '/api/pedidos/9' ? order : [order, raw(10, 'PENDIENTE', { cliente: 'Ana' })]); };
  useOrders([]);
  const container = await mount(t, '/dashboard/orders?q=Ana');
  await settle();
  await act(async () => reactProps(statusButton(container, 'Listos')).onClick());
  await act(async () => reactProps(opener(container, 9)).onClick());
  const lists = calls.filter((path) => path.startsWith('/api/pedidos?')).length;
  await act(async () => reactProps(buttons(container).find((node) => node.textContent === 'Actualizar pedidos')).onClick());
  await settle();
  assert.ok(calls.filter((path) => path.startsWith('/api/pedidos?')).length > lists);
  const dialog = elements(container, (node) => node.localName === 'dialog')[0];
  assert.equal(dialog?.open, true);
  assert.match(dialog.textContent, /Pedido #9/);
  assert.equal(reactProps(statusButton(container, 'Listos'))['aria-pressed'], true);
  assert.equal(statusButton(container, 'Nuevos').getAttribute('aria-label'), 'Nuevos: 1 pedido');
});

test('sin pedidos ni resultados muestra un único vacío comprensible', async (t) => {
  useOrders([]);
  const empty = await mount(t);
  assert.match(empty.textContent, /No hay pedidos activos en este momento/);
  assert.equal(sections(empty).length, 0);
  globalThis.fetch = async () => response([]);
  const search = await mount(t, '/dashboard/orders?q=Zoe');
  await settle();
  assert.match(search.textContent, /Sin resultados para «Zoe»/);
});

test('cargando y error se distinguen de un estado vacío', async (t) => {
  data.state = { orders: [], ordersStatus: 'loading', ordersError: null };
  const loading = await mount(t);
  assert.match(loading.textContent, /Consultando pedidos/);
  assert.equal(statusButton(loading, 'Nuevos').getAttribute('aria-label'), 'Nuevos: cantidad sin consultar');
  assert.match(sections(loading)[0].textContent, /Consultando/);
  data.state = { orders: [], ordersStatus: 'error', ordersError: 'No pudimos actualizar los pedidos.' };
  const failed = await mount(t);
  assert.match(failed.textContent, /No pudimos actualizar los pedidos/);
  assert.match(sections(failed)[0].textContent, /Información sin actualizar/);
});


test('la agrupación usa pagos completos y no confunde confirmar, efectivo o un comprobante con pagar', () => {
  const paid = { neto_cobrado: '1000', saldo_pendiente: '0' };
  const orders = [
    raw(1, 'PENDIENTE', paid), raw(2, 'CONFIRMADO'),
    raw(3, 'PENDIENTE', { neto_cobrado: '500', saldo_pendiente: '500' }),
    raw(4, 'PENDIENTE', { metodo_pago_acordado: 'TRANSFERENCIA', pagos: [{ estado: 'PENDIENTE', monto: '1000' }] }),
    raw(5, 'PENDIENTE', { metodo_pago_acordado: 'EFECTIVO' }),
    raw(6, 'EN_PREPARACION', paid), raw(7, 'LISTO', paid), raw(8, 'EN_CAMINO', paid),
  ].map(model.mapOrder);
  const groups = board.groupOrders(orders, board.scopeStates('active'), Date.now());
  assert.deepEqual(groups.PAGADOS.orders.map((order) => order.id), [1]);
  assert.deepEqual(groups.PENDIENTE.orders.map((order) => order.id).sort(), [2, 3, 4, 5]);
  assert.equal(groups.EN_PREPARACION.count, 1); assert.equal(groups.LISTO.count, 1); assert.equal(groups.EN_CAMINO.count, 1);
  assert.equal(Object.values(groups).reduce((sum, group) => sum + group.count, 0), 8);
  assert.equal(orders[0].estado, 'PENDIENTE');
  assert.equal(model.ORDER_STATES.some(([id]) => id === 'PAGADOS'), false, 'Pagados no es un estado API');
});

test('pago exacto requiere importes presentes, conciliados y consistentes, sin errores de decimales', () => {
  assert.equal(model.isOrderPaid(raw(1, 'PENDIENTE', { total: '0.30', neto_cobrado: '0.30', saldo_pendiente: '0' })), true);
  for (const extra of [
    { total: '0.30', neto_cobrado: '0.29', saldo_pendiente: '0.01' },
    { neto_cobrado: null, saldo_pendiente: '0' }, { total: null, neto_cobrado: '1000', saldo_pendiente: '0' },
    { neto_cobrado: '1000', saldo_pendiente: null }, { neto_cobrado: '', saldo_pendiente: '0' },
    { neto_cobrado: '1000', saldo_pendiente: '1' }, { neto_cobrado: 'Infinity', saldo_pendiente: '0' },
  ]) assert.equal(model.isOrderPaid(raw(1, 'PENDIENTE', extra)), false);
});

test('pagar o devolver reagrupa sin recargar ni duplicar tarjetas y conserva la etapa física', async (t) => {
  useOrders([raw(41, 'PENDIENTE')]);
  const container = await mount(t);
  assert.match(statusButton(container, 'Nuevos').getAttribute('aria-label'), /1 pedido/);
  assert.match(statusButton(container, 'Pagados').getAttribute('aria-label'), /0 pedidos/);
  useOrders([raw(41, 'PENDIENTE', { version: 2, neto_cobrado: '1000', saldo_pendiente: '0' })]);
  await container.rerender();
  assert.match(statusButton(container, 'Nuevos').getAttribute('aria-label'), /0 pedidos/);
  assert.match(statusButton(container, 'Pagados').getAttribute('aria-label'), /1 pedido/);
  assert.equal(buttons(container).filter((node) => node.textContent === 'Abrir pedido #41').length, 1);
  useOrders([raw(41, 'PENDIENTE', { version: 3, neto_cobrado: '500', saldo_pendiente: '500' })]);
  await container.rerender();
  assert.match(statusButton(container, 'Nuevos').getAttribute('aria-label'), /1 pedido/);
  useOrders([raw(41, 'EN_PREPARACION', { version: 4, neto_cobrado: '1000', saldo_pendiente: '0' })]);
  await container.rerender();
  assert.match(statusButton(container, 'Pagados').getAttribute('aria-label'), /0 pedidos/);
  assert.match(statusButton(container, 'En preparación').getAttribute('aria-label'), /1 pedido/);
});

test('el retiro listo requiere cobertura conciliada, sin saltar cocina ni delivery', () => {
  const options = (order) => model.stateCommands(order, 'EMPLEADO').map((command) => command.estado);
  assert.equal(options(raw(1, 'LISTO', { metodo_pago_acordado: 'EFECTIVO' })).includes('ENTREGADO'), false);
  assert.ok(options(raw(1, 'LISTO', { metodo_pago_acordado: 'EFECTIVO', neto_cobrado: '1000', saldo_pendiente: '0' })).includes('ENTREGADO'));
  assert.ok(options(raw(1, 'LISTO', { metodo_pago_acordado: 'TRANSFERENCIA', neto_cobrado: '1000', saldo_pendiente: '0' })).includes('ENTREGADO'));
  assert.equal(options(raw(1, 'LISTO', { metodo_pago_acordado: 'TRANSFERENCIA' })).includes('ENTREGADO'), false);
  assert.equal(options(raw(1, 'LISTO', { metodo_pago_acordado: 'TRANSFERENCIA', neto_cobrado: '500', saldo_pendiente: '500' })).includes('ENTREGADO'), false);
  assert.equal(options(raw(1, 'PENDIENTE', { neto_cobrado: '1000', saldo_pendiente: '0' })).includes('ENTREGADO'), false);
  assert.equal(options(raw(1, 'LISTO', { tipo_entrega: 'DELIVERY' })).includes('ENTREGADO'), false);
});
