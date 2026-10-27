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
  assert.match(screen.getData().state.inventoryError, /conectar/);
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
test('un acuse vacío no se confirma con un pedido anterior válido', async (t) => {
  globalThis.fetch = async (path) => response(path.endsWith('/1') ? { id: 1, numero: 1, version: 1, estado: 'PENDIENTE', items: [], historial: [] } : []);
  const screen = await mount(t);
  let success = 0;
  await act(async () => { screen.getData().startOrderOperation({ id: 1, operation: async () => ({}), onSuccess: () => success++ }); });
  assert.equal(success, 0);
  assert.equal(screen.getData().orderOperations[0].status, 'error');
});
for (const [operation, payload] of [['createProduct', { name: 'Burger' }], ['createIngredient', { name: 'Pan', stock: 0, min: 1 }]]) {
  test(`${operation} no confirma un objeto JSON vacío`, async (t) => {
    globalThis.fetch = async (_path, options = {}) => response(options.method ? {} : []);
    const screen = await mount(t);
    await act(async () => { await assert.rejects(screen.getData()[operation](payload), /confirmar|respuesta/i); });
  });
}
