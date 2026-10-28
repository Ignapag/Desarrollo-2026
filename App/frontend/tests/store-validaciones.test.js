import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { act, createElement, useLayoutEffect } from 'react';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom } from './minimal-dom.js';
let server, dom, createRoot, DataProvider, useData, setUser;
const originalFetch = globalThis.fetch;
const user = { id: 1, backendRole: 'EMPLEADO', permisos: ['stock.ver', 'stock.gestionar', 'stock.reponer', 'productos.gestionar'] };
const response = (body) => ({ ok: true, status: 200, json: async () => body });
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'auth-store-validation', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'let user; export const setUser=(next)=>{user=next}; export const useAuth=()=>({user});';
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ DataProvider, useData } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
  ({ setUser } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });
async function mount(t) {
  setUser(user);
  let data;
  const snapshots = [];
  function Probe() { const current = useData(); useLayoutEffect(() => { data = current; snapshots.push(current.state.inventory); }); return null; }
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const render = () => root.render(createElement(DataProvider, null, createElement(Probe)));
  await act(async () => render());
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return { getData: () => data, render, snapshots };
}
for (const operation of ['updateRecipe', 'deactivateProduct', 'replenishIngredient']) {
  test(`${operation} no confirma un objeto JSON vacío`, async (t) => {
    globalThis.fetch = async (_path, options = {}) => response(options.method ? {} : []);
    const screen = await mount(t);
    await act(async () => { await assert.rejects(screen.getData()[operation](1, {}), /confirmar|respuesta/i); });
  });
}
test('el inventario privado se oculta en el primer render de otra sesión', async (t) => {
  globalThis.fetch = async () => response([{ id: 1, nombre: 'Privado', cantidad_actual: '9', umbral_minimo: '0' }]);
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  assert.equal(screen.getData().state.inventory.length, 1);
  screen.snapshots.length = 0;
  setUser({ id: 2, backendRole: 'EMPLEADO', permisos: [] });
  await act(async () => screen.render());
  assert.equal(screen.snapshots[0].length, 0);
});
test('un handler de la sesión anterior no envía escrituras con la cookie nueva', async (t) => {
  const calls = [];
  globalThis.fetch = async (path, options = {}) => { calls.push([path, options.method]); return response({ id: 1, nombre: 'Producto' }); };
  const screen = await mount(t);
  const previous = screen.getData();
  setUser({ ...user, id: 2 });
  await act(async () => screen.render());
  let error;
  await act(async () => { try { await previous.createProduct({ name: 'Privado' }); } catch (caught) { error = caught; } });
  assert.match(error?.message || '', /sesión|acceso/i);
  assert.equal(calls.filter(([, method]) => method === 'POST').length, 0);
});
test('una carga inicial de inventario fallida conserva un error reintentable', async (t) => {
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
  const screen = await mount(t);
  await act(async () => { await assert.rejects(screen.getData().refreshInventory()); });
  assert.equal(screen.getData().state.inventoryStatus, 'error');
  assert.match(screen.getData().state.inventoryError, /inventario/);
});

test('el tablero nunca publica excepciones internas de una operación fallida', async (t) => {
  globalThis.fetch = async () => response([]);
  const screen = await mount(t);
  await act(async () => { screen.getData().startOrderOperation({ id: 1, operation: async () => { throw new Error('SQL /private password=secreto'); } }); });
  const failure = screen.getData().orderOperations[0];
  assert.equal(failure.status, 'error');
  assert.doesNotMatch(failure.message, /SQL|private|password/);
  assert.match(failure.message, /Revisá el pedido antes de reintentar/);
});

test('una respuesta inesperada de clientes se rechaza antes de almacenarla', async (t) => {
  globalThis.fetch = async () => response({ clientes: 'SQL /private' });
  const screen = await mount(t);
  // Esta cuenta obtiene el permiso sólo para probar la lectura real del store.
  setUser({ ...user, permisos: [...user.permisos, 'clientes.ver'] });
  await act(async () => screen.render());
  await act(async () => assert.rejects(screen.getData().getCustomers('/api/reportes/clientes'), /clientes/));
  assert.equal(screen.getData().cachedCustomers('/api/reportes/clientes'), null);
});
test('403 de inventario retira el snapshot que dejó de estar autorizado', async (t) => {
  let denied = false;
  globalThis.fetch = async () => denied ? { status: 403, ok: false, json: async () => ({ mensaje: 'Sin acceso' }) } : response([{ id: 1, nombre: 'Privado', cantidad_actual: '9', umbral_minimo: '1' }]);
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  denied = true;
  await act(async () => { await assert.rejects(screen.getData().refreshInventory(undefined, true)); });
  assert.equal(screen.getData().state.inventory.length, 0);
});
test('una operación con acuse y reconciliación incompletos no anuncia éxito', async (t) => {
  globalThis.fetch = async (path) => response(path.endsWith('/1') ? {} : []);
  const screen = await mount(t);
  let success = 0;
  await act(async () => { screen.getData().startOrderOperation({ id: 1, operation: async () => ({}), onSuccess: () => success++ }); });
  assert.equal(success, 0);
  assert.equal(screen.getData().orderOperations[0].status, 'error');
  assert.doesNotMatch(screen.getData().orderOperations[0].message, /La acción se registró/);
});
for (const result of [{}, { unexpected: true }, { mensaje: 'Operación fallida' }, { pedido_id: 1, envio_id: 2 }]) {
test(`un acuse inesperado ${JSON.stringify(result)} no se confirma con un pedido anterior válido`, async (t) => {
  globalThis.fetch = async (path) => response(path.endsWith('/1') ? { id: 1, numero: 1, version: 1, estado: 'PENDIENTE', items: [], historial: [] } : []);
  const screen = await mount(t);
  let success = 0;
  await act(async () => { screen.getData().startOrderOperation({ id: 1, operation: async () => result, onSuccess: () => success++ }); });
  assert.equal(success, 0);
  assert.equal(screen.getData().orderOperations[0].status, 'error');
});
}

test('un movimiento de reparto confirmado permite consultar el pedido actualizado', async (t) => {
  const order = { id: 1, numero: 1, version: 2, estado: 'LISTO', items: [], historial: [] };
  globalThis.fetch = async (path) => response(path.endsWith('/1') ? order : []);
  const screen = await mount(t);
  let success = 0;
  await act(async () => { screen.getData().startOrderOperation({ id: 1, operation: async () => ({ pedido_id: 1, envio_id: 2, viaje_id: 3 }), onSuccess: () => success++ }); });
  assert.equal(success, 1);
  assert.equal(screen.getData().orderOperations[0].status, 'success');
});
for (const [operation, payload] of [['createProduct', { name: 'Burger' }], ['createIngredient', { name: 'Pan', stock: 0, min: 1 }]]) {
  test(`${operation} no confirma un objeto JSON vacío`, async (t) => {
    globalThis.fetch = async (_path, options = {}) => response(options.method ? {} : []);
    const screen = await mount(t);
    await act(async () => { await assert.rejects(screen.getData()[operation](payload), /confirmar|respuesta/i); });
  });
}
test('el costo de un insumo se envía como decimal exacto y se publica el valor confirmado', async (t) => {
  const calls = [];
  const row = { id: 7, nombre: 'Tomate', unidad_medida: 'GR', cantidad_actual: '50', umbral_minimo: '10', costo_unitario: '0.00', nivel: 'NORMAL' };
  globalThis.fetch = async (path, options = {}) => {
    calls.push([path, options.method || 'GET', options.body]);
    if (options.method === 'PATCH') { row.costo_unitario = '4.55'; return response(row); }
    return response([row]);
  };
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  assert.equal(screen.getData().state.inventory[0].cost, 0);
  await act(async () => { await screen.getData().updateIngredientCost(7, '4.55'); });
  const patch = calls.find(([, method]) => method === 'PATCH');
  assert.equal(patch[0], '/api/stock/ingredientes/7');
  assert.deepEqual(JSON.parse(patch[2]), { costo_unitario: '4.55' });
  assert.equal(screen.getData().state.inventory[0].cost, 4.55);
});
test('updateIngredientCost no confirma una respuesta de otro insumo ni un objeto vacío', async (t) => {
  for (const body of [{}, { id: 8, costo_unitario: '1', cantidad_actual: '1', umbral_minimo: '1' }]) {
    globalThis.fetch = async (_path, options = {}) => response(options.method ? body : []);
    const screen = await mount(t);
    await act(async () => { await assert.rejects(screen.getData().updateIngredientCost(7, '1'), /confirmar/i); });
  }
});

// post devuelve la respuesta HTTP simulada de la reposición; un 2xx actualiza el saldo servido.
function stockApi({ post }) {
  const calls = [];
  let stock = '200';
  globalThis.fetch = async (path, options = {}) => {
    calls.push([path, options.method || 'GET', options.body]);
    if (path.startsWith('/api/stock/ingredientes?')) return response([{ id: 3, nombre: 'Carne', unidad_medida: 'GR', cantidad_actual: stock, umbral_minimo: '100', nivel: 'NORMAL' }]);
    if (path === '/api/stock/ingredientes/3/reposiciones') {
      const result = await post();
      if (result.ok) stock = (await result.json()).saldo_resultante ?? stock;
      return result;
    }
    return response([]);
  };
  return { calls, posts: () => calls.filter(([, method]) => method === 'POST') };
}
test('reposición manual envía el decimal exacto y publica el saldo y movimiento que devuelve la API', async (t) => {
  const api = stockApi({ post: async () => response({ ingrediente_id: 3, movimiento_id: 41, saldo_resultante: '2690.5' }) });
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  let result;
  await act(async () => { result = await screen.getData().replenishIngredient(3, '2500.5'); });
  assert.deepEqual(JSON.parse(api.posts()[0][2]), { cantidad: '2500.5', origen: 'PANEL_WEB' });
  assert.deepEqual(result, { stock: 2690.5, movementId: 41 });
  assert.equal(screen.getData().state.inventory[0].stock, 2690.5);
});
test('reposición rechazada con 403 revierte el saldo optimista y no se reintenta', async (t) => {
  const api = stockApi({ post: async () => ({ ok: false, status: 403, json: async () => ({ mensaje: 'Sin permiso' }) }) });
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  await act(async () => { await assert.rejects(screen.getData().replenishIngredient(3, '50'), /No tenés acceso/); });
  assert.equal(api.posts().length, 1);
  assert.equal(screen.getData().state.inventory[0].stock, 200);
});
test('reposición con conexión cortada queda incierta y no se reintenta sola', async (t) => {
  const api = stockApi({ post: async () => { throw new TypeError('Failed to fetch'); } });
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  let error;
  await act(async () => { try { await screen.getData().replenishIngredient(3, '50'); } catch (caught) { error = caught; } });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
  assert.equal(error?.uncertain, true);
  assert.match(error.message, /Comprobá su estado antes de repetir/);
  assert.equal(api.posts().length, 1);
});
test('una confirmación de reposición incompleta se marca como incierta', async (t) => {
  stockApi({ post: async () => response({ ingrediente_id: 3 }) });
  const screen = await mount(t);
  await act(async () => screen.getData().refreshInventory());
  let error;
  await act(async () => { try { await screen.getData().replenishIngredient(3, '5'); } catch (caught) { error = caught; } });
  assert.equal(error?.uncertain, true);
});
test('sin stock.reponer la reposición no llega a la API', async (t) => {
  const api = stockApi({ post: async () => response({ ingrediente_id: 3, movimiento_id: 1, saldo_resultante: '201' }) });
  const screen = await mount(t);
  setUser({ ...user, permisos: ['stock.ver'] });
  await act(async () => screen.render());
  await act(async () => { await assert.rejects(screen.getData().replenishIngredient(3, '1'), /acceso/); });
  assert.equal(api.posts().length, 0);
});
