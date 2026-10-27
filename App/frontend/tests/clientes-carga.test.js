import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement, useLayoutEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { createTestServer as createServer } from './vite-test-server.js';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let DataProvider;
let useData;
let Customers;
let OrderDetail;
let setTestUser;
const previousFetch = globalThis.fetch;
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const row = { id: 71, nombre: 'Cliente real reciente', telefono: '5492215550101', zona_frecuente: 'Retiro en local', pedidos_count: 3, primer_pedido_en: '2026-10-17T20:00:00Z', ultimo_pedido_en: '2026-10-18T01:00:00Z' };

before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, plugins: [{ name: 'sesion-clientes', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "let user={id:1,role:'admin',backendRole:'EMPLEADO',permisos:['pedidos.ver','pedidos.cambiar_estado','clientes.ver','stock.ver','stock.gestionar','stock.reponer','productos.gestionar','pagos.ver','pagos.registrar','pagos.conciliar','reportes.ver']}; export const setTestUser=(value)=>{user=value}; export const useAuth=()=>({user});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ DataProvider, useData } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
  ({ default: Customers } = await server.ssrLoadModule('/src/management/Customers.jsx'));
  ({ default: OrderDetail } = await server.ssrLoadModule('/src/fulfillment/OrderDetail.jsx'));
  ({ setTestUser } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });

async function mount(t, child, path = '/') {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const routerProps = { initialEntries: [path] };
  await act(async () => root.render(createElement(MemoryRouter, routerProps, createElement(DataProvider, null, child))));
  container.rerender = () => root.render(createElement(MemoryRouter, routerProps, createElement(DataProvider, null, child)));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}

test('abrir personal carga pedidos sin descargar catálogo ni inventario que no se están usando', async (t) => {
  const calls = [];
  globalThis.fetch = async (path) => { calls.push(path); return response([]); };
  await mount(t, null);
  assert.deepEqual(calls, ['/api/pedidos?activos=true']);
});

test('clientes muestra la identidad real de la API y permite abrir sus pedidos por ID', async (t) => {
  globalThis.fetch = async (path) => response(path.startsWith('/api/reportes/clientes') ? { clientes: [row], total: 1, limite: 50, desplazamiento: 0 } : []);
  const container = await mount(t, createElement(Customers));
  assert.match(container.textContent, /Cliente real reciente/);
  assert.match(container.textContent, /3 pedidos/);
  assert.doesNotMatch(container.textContent, /Martina Gómez|Lucas Fernández/);
  const link = elements(container, (node) => node.localName === 'a' && node.textContent.includes('Ver pedidos'))[0];
  assert.match(link?.getAttribute('href') || '', /cliente_id=71/);
});

test('una página fuera del total no anuncia un rango imposible ni un directorio vacío', async (t) => {
  globalThis.fetch = async (path) => response(path.startsWith('/api/reportes/clientes') ? { clientes: [], total: 1, limite: 50, desplazamiento: 100 } : []);
  const container = await mount(t, createElement(Customers), '/dashboard/customers?desplazamiento=100');
  assert.match(container.textContent, /No hay clientes en esta página/);
  assert.doesNotMatch(container.textContent, /No hay clientes registrados|101–100/);
  const previous = elements(container, (node) => node.localName === 'button' && node.textContent === 'Anterior')[0];
  assert.equal(previous.disabled, false);
});

test('un error de clientes muestra reintento y nunca rellena personas de muestra', async (t) => {
  globalThis.fetch = async (path) => {
    if (path.startsWith('/api/reportes/clientes')) throw new Error('No disponible');
    return response([]);
  };
  const container = await mount(t, createElement(Customers));
  assert.match(container.textContent, /No se pudieron cargar los clientes/);
  assert.doesNotMatch(container.textContent, /Martina Gómez|Lucas Fernández|No hay clientes/);
});

test('un error del directorio no se muestra en la siguiente sesión', async (t) => {
  globalThis.fetch = async (path) => {
    if (path.startsWith('/api/reportes/clientes')) throw new Error('Error exclusivo de la sesión anterior');
    return response([]);
  };
  const container = await mount(t, createElement(Customers));
  assert.match(container.textContent, /Error exclusivo de la sesión anterior/);
  const waiting = deferred();
  globalThis.fetch = async (path) => path.startsWith('/api/reportes/clientes') ? waiting.promise : response([]);
  setTestUser({ id: 2, role: 'admin', backendRole: 'EMPLEADO', permisos: ['clientes.ver'] });
  t.after(() => setTestUser({ id: 1, role: 'admin', backendRole: 'EMPLEADO', permisos: ['pedidos.ver', 'pedidos.cambiar_estado', 'clientes.ver', 'stock.ver', 'stock.gestionar', 'stock.reponer', 'productos.gestionar', 'pagos.ver', 'pagos.registrar', 'pagos.conciliar', 'reportes.ver'] }));
  await act(async () => container.rerender());
  assert.doesNotMatch(container.textContent, /Error exclusivo de la sesión anterior/);
  assert.match(container.textContent, /Consultando clientes/);
  await act(async () => waiting.resolve(response({ clientes: [], total: 0 })));
});

test('cargas de catálogo concurrentes comparten solicitud y conservan caché al volver', async (t) => {
  const waiting = deferred();
  let calls = 0;
  let data;
  globalThis.fetch = async (path) => { if (path === '/api/productos') { calls += 1; return waiting.promise; } return response([]); };
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  await mount(t, createElement(Capture));
  assert.equal(typeof data.refreshCatalog, 'function');
  let one;
  let two;
  await act(async () => { one = data.refreshCatalog(); two = data.refreshCatalog(); });
  assert.equal(calls, 1);
  await act(async () => { waiting.resolve(response([])); await Promise.all([one, two]); });
  await act(async () => data.refreshCatalog());
  assert.equal(calls, 1);
});

test('actualizar clientes conserva las filas mientras espera la respuesta nueva', async (t) => {
  const waiting = deferred();
  let calls = 0;
  globalThis.fetch = async (path) => {
    if (path.startsWith('/api/reportes/clientes')) { calls += 1; return calls === 1 ? response({ clientes: [row], total: 1, limite: 50, desplazamiento: 0 }) : waiting.promise; }
    return response([]);
  };
  const container = await mount(t, createElement(Customers));
  const refresh = elements(container, (node) => node.localName === 'button' && node.textContent === 'Actualizar clientes')[0];
  assert.ok(refresh);
  await act(async () => reactProps(refresh).onClick());
  assert.match(container.textContent, /Cliente real reciente/);
  await act(async () => { waiting.resolve(response({ clientes: [{ ...row, pedidos_count: 4 }], total: 1, limite: 50, desplazamiento: 0 })); });
  assert.match(container.textContent, /4 pedidos/);
});

test('un permiso rechazado retira las filas del directorio ya cargadas', async (t) => {
  globalThis.fetch = async (path) => response(path.startsWith('/api/reportes/clientes') ? { clientes: [row], total: 1 } : []);
  const container = await mount(t, createElement(Customers));
  assert.match(container.textContent, /Cliente real reciente/);
  globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({ detail: 'Directorio sin acceso' }) });
  const refresh = elements(container, (node) => node.localName === 'button' && node.textContent === 'Actualizar clientes')[0];
  await act(async () => reactProps(refresh).onClick());
  assert.match(container.textContent, /Directorio sin acceso/);
  assert.doesNotMatch(container.textContent, /Cliente real reciente/);
});

test('un GET anterior no resucita productos ni pisa una reposición confirmada', async (t) => {
  const oldCatalog = deferred();
  const oldStock = deferred();
  const product = { id: 7, nombre: 'Real', precio_base: 100, activo: true };
  const ingredient = { id: 9, nombre: 'Pan', cantidad_actual: 10, umbral_minimo: 2, nivel: 'NORMAL' };
  let catalogReads = 0;
  let stockReads = 0;
  let removed = false;
  let replenished = false;
  let data;
  globalThis.fetch = async (path, options = {}) => {
    if (path === '/api/productos') {
      catalogReads += 1;
      return catalogReads === 2 ? oldCatalog.promise : response(removed ? [] : [product]);
    }
    if (path.startsWith('/api/stock/ingredientes?')) {
      stockReads += 1;
      return stockReads === 2 ? oldStock.promise : response([{ ...ingredient, cantidad_actual: replenished ? 11 : 10 }]);
    }
    if (options.method === 'PATCH') { removed = true; return response({ ...product, activo: false }); }
    if (path.endsWith('/reposiciones')) { replenished = true; return response({ ingrediente_id: 9, movimiento_id: 1, saldo_resultante: '11' }); }
    return response([]);
  };
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  await mount(t, createElement(Capture));
  await act(async () => { await Promise.all([data.refreshCatalog(), data.refreshInventory()]); });
  let catalogPending;
  let stockPending;
  await act(async () => {
    catalogPending = data.refreshCatalog(undefined, true);
    stockPending = data.refreshInventory(undefined, true);
  });
  await act(async () => { await Promise.all([data.deactivateProduct(7), data.replenishIngredient(9, 1)]); });
  assert.equal(data.state.catalog.length, 0);
  assert.equal(data.state.inventory[0].stock, 11);
  await act(async () => {
    oldCatalog.resolve(response([product]));
    oldStock.resolve(response([ingredient]));
    await Promise.all([catalogPending, stockPending]);
  });
  assert.equal(data.state.catalog.length, 0);
  assert.equal(data.state.inventory[0].stock, 11);
});

test('abortar la pantalla no descarta el valor de clientes ya resuelto', async (t) => {
  let calls = 0;
  let data;
  globalThis.fetch = async (path) => {
    if (path.startsWith('/api/reportes/clientes')) { calls += 1; return response({ clientes: [row], total: 1 }); }
    return response([]);
  };
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  await mount(t, createElement(Capture));
  const controller = new AbortController();
  const path = '/api/reportes/clientes?limite=50';
  await act(async () => data.getCustomers(path, controller.signal));
  controller.abort();
  await act(async () => data.getCustomers(path));
  assert.equal(calls, 1);
});

test('el sondeo de pedidos sólo consulta cuando hay una pantalla suscripta y visible', async (t) => {
  const previousInterval = window.setInterval;
  const previousClear = window.clearInterval;
  let poll;
  window.setInterval = (callback) => { poll = callback; return 1; };
  window.clearInterval = () => {};
  t.after(() => { window.setInterval = previousInterval; window.clearInterval = previousClear; document.hidden = false; });
  let calls = 0;
  let data;
  globalThis.fetch = async () => { calls += 1; return response([]); };
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  await mount(t, createElement(Capture));
  assert.equal(calls, 1);
  await act(async () => poll());
  assert.equal(calls, 1);
  const unsubscribe = data.watchOrders();
  await act(async () => poll());
  assert.equal(calls, 2);
  document.hidden = true;
  await act(async () => poll());
  assert.equal(calls, 2);
  document.hidden = false;
  unsubscribe();
  await act(async () => poll());
  assert.equal(calls, 2);
});

test('abrir detalle muestra el pedido conocido mientras se comprueba la versión vigente', async (t) => {
  const waiting = deferred();
  const order = { id: 17, numero: 88, version: 3, estado: 'PENDIENTE', tipo_entrega: 'RETIRO', cliente: 'Cliente conocido', metodo_pago_acordado: 'EFECTIVO', total: '12000', saldo_pendiente: '12000', neto_cobrado: '0', items: [], pagos: [], historial: [] };
  let data;
  globalThis.fetch = async (path) => path === '/api/pedidos/17' ? waiting.promise : response([order]);
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return current.state.orders.length ? createElement(OrderDetail, { id: 17, onClose() {} }) : null; }
  const container = await mount(t, createElement(Capture));
  assert.equal(data.state.orders.length, 1);
  assert.match(container.textContent, /Pedido #88/);
  assert.match(container.textContent, /Cliente conocido/);
  await act(async () => { waiting.resolve(response({ ...order, numero: 89 })); });
  assert.match(container.textContent, /Pedido #89/);
});

test('una escritura pendiente de la sesión anterior no bloquea recursos de la nueva', async (t) => {
  const waiting = deferred();
  let data;
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'PATCH') return waiting.promise;
    if (path === '/api/productos') return response([{ id: 7, nombre: 'Vigente', precio_base: 100, activo: true }]);
    if (path.startsWith('/api/reportes/clientes')) return response({ clientes: [row], total: 1 });
    return response([]);
  };
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  const container = await mount(t, createElement(Capture));
  const path = '/api/reportes/clientes?limite=50';
  await act(async () => { await data.refreshCatalog(); await data.getCustomers(path); });
  let pending;
  await act(async () => { pending = data.deactivateProduct(7); });
  setTestUser({ id: 2, role: 'admin', backendRole: 'EMPLEADO' });
  t.after(() => setTestUser({ id: 1, role: 'admin', backendRole: 'EMPLEADO' }));
  await act(async () => container.rerender());
  assert.equal(data.cachedCustomers(path), null);
  await act(async () => data.refreshCatalog());
  assert.equal(data.state.catalogStatus, 'ready');
  assert.equal(data.state.catalog[0].name, 'Vigente');
  await act(async () => { waiting.resolve(response({ id: 7, activo: false })); await pending; });
  assert.equal(data.state.catalog.length, 1);
});
