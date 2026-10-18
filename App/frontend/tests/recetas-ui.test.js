import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let Catalog;
let DataProvider;
const previousFetch = globalThis.fetch;
const product = { id: 1, categoria_id: 1, categoria: 'Hamburguesas', nombre: 'Cheese', precio_base: '100', activo: true, disponible: true, variantes: [] };
const inventory = [{ id: 10, nombre: 'Tomate', unidad_medida: 'UNIDAD', cantidad_actual: '10', umbral_minimo: '1', nivel: 'NORMAL' }, { id: 11, nombre: 'Pan', unidad_medida: 'UNIDAD', cantidad_actual: '10', umbral_minimo: '1', nivel: 'NORMAL' }];
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const button = (container, text) => elements(container, (node) => node.localName === 'button' && (node.textContent.trim() === text || reactProps(node)['aria-label'] === text))[0];
const input = (container, id) => elements(container, (node) => node.getAttribute?.('id') === id)[0];
async function change(node, value) { await act(async () => reactProps(node).onChange({ target: { value } })); }

before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, cacheDir: `node_modules/.vite-recetas-test-${process.pid}`, plugins: [{ name: 'auth-recetas', enforce: 'pre', resolveId(source) { if (source === 'sonner') return '\0sonner-recetas-test'; return null; }, load(id) {
    if (id === '\0sonner-recetas-test') return 'export const toast={error(){},success(){},info(){}};';
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "const user={id:1,role:'admin',backendRole:'ADMINISTRADOR'}; export const useAuth=()=>({user});";
    return null;
  } }, react()], ssr: { noExternal: ['sonner'] }, server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Catalog } = await server.ssrLoadModule('/src/management/Catalog.jsx'));
  ({ DataProvider } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });

async function mount(t, extraFetch = () => undefined) {
  globalThis.fetch = async (path, options = {}) => {
    const extra = extraFetch(path, options);
    if (extra) return extra;
    return response(path === '/api/productos' ? [product] : path.startsWith('/api/stock/ingredientes') ? inventory : []);
  };
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(MemoryRouter, null, createElement(DataProvider, null, createElement(Catalog)))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}

test('crear una hamburguesa envía la receta completa y convierte un cuarto sin perder precisión', async (t) => {
  let sent;
  const container = await mount(t, (path, options) => {
    if (path === '/api/productos' && options.method === 'POST') { sent = JSON.parse(options.body); return response({ ...product, id: 2, nombre: 'Nueva' }); }
    return undefined;
  });
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  await change(input(container, 'new-product-name'), 'Nueva');
  await change(input(container, 'new-product-price'), '100');
  const selects = () => elements(container, (node) => node.localName === 'select' && reactProps(node)['aria-label'] !== '');
  const ingredientSelects = () => selects().filter((node) => node.getAttribute('id')?.includes('-ingredient-'));
  await change(ingredientSelects()[0], '10');
  const quantities = () => elements(container, (node) => node.localName === 'input' && reactProps(node).placeholder === 'Ej.: 0,25 o 1/4');
  await change(quantities()[0], '1/4');
  assert.match(container.textContent, /0,25 unidad por producto/);
  await act(async () => reactProps(button(container, 'Agregar ingrediente')).onClick());
  await change(ingredientSelects()[1], '11');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.deepEqual(sent.ingredientes.map((row) => [row.ingrediente_id, row.cantidad_requerida]), [[10, '0.25'], [11, '1']]);
});

test('editar la receta guarda cantidades por variante con control de versión', async (t) => {
  let sent;
  const recipe = { producto_id: 1, actualizado_en: '2026-10-18T10:00:00Z', ingredientes: [{ ingrediente_id: 10, nombre: 'Tomate', unidad_medida: 'UNIDAD', cantidad_requerida: '0.25', es_base: true }], variantes: [{ nombre: 'Simple', precio: '100', ingredientes: [{ ingrediente_id: 10, cantidad_requerida: '0.25', es_base: true }] }, { nombre: 'Doble', precio: '150', ingredientes: [{ ingrediente_id: 10, cantidad_requerida: '0.5', es_base: true }] }] };
  const container = await mount(t, (path, options) => {
    if (path.endsWith('/1/receta')) { if (options.method === 'PUT') sent = JSON.parse(options.body); return response(recipe); }
    return undefined;
  });
  await act(async () => reactProps(button(container, 'Editar receta de Cheese')).onClick());
  const fields = elements(container, (node) => node.localName === 'input' && reactProps(node).placeholder === 'Ej.: 0,25 o 1/4');
  await change(fields[1], '3/4');
  await act(async () => reactProps(button(container, 'Guardar receta')).onClick());
  assert.equal(sent.actualizado_en_esperado, recipe.actualizado_en);
  assert.deepEqual(sent.variantes.map((row) => row.ingredientes[0].cantidad_requerida), ['0.25', '0.75']);
  assert.equal(Object.hasOwn(sent.variantes[0], 'precio'), false);
});

test('crear variantes conserva cada cantidad y bloquea una fracción inválida antes del POST', async (t) => {
  let sent;
  const container = await mount(t, (path, options) => {
    if (path === '/api/productos' && options.method === 'POST') { sent = JSON.parse(options.body); return response(product); }
  });
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  await change(input(container, 'new-product-name'), 'Nueva');
  await change(input(container, 'new-product-price'), '100');
  const ingredient = elements(container, (node) => node.localName === 'select' && node.getAttribute('id')?.includes('-ingredient-'))[0];
  await change(ingredient, '10');
  await act(async () => reactProps(button(container, 'Usar variantes')).onClick());
  await act(async () => reactProps(button(container, 'Agregar variante')).onClick());
  const names = elements(container, (node) => node.localName === 'input' && node.getAttribute('id')?.includes('-variant-'));
  await change(names[1], 'Doble');
  const quantities = () => elements(container, (node) => node.localName === 'input' && reactProps(node).placeholder === 'Ej.: 0,25 o 1/4');
  await change(quantities()[0], '1/4');
  await change(quantities()[1], '1/0');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.equal(sent, undefined);
  assert.match(container.textContent, /denominador/);
  await change(quantities()[1], '3/4');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.deepEqual(sent.variantes.map((variant) => [variant.nombre, variant.ingredientes[0].cantidad_requerida]), [['Simple', '0.25'], ['Doble', '0.75']]);
});

test('un conflicto de receta conserva la edición y las unidades hasta recarga explícita', async (t) => {
  const recipe = { producto_id: 1, actualizado_en: '2026-10-18T10:00:00Z', ingredientes: [{ ingrediente_id: 22, nombre: 'Tomate en gramos', unidad_medida: 'GR', cantidad_requerida: '25', es_base: false }], variantes: [] };
  const container = await mount(t, (path, options) => {
    if (path.endsWith('/1/receta')) return options.method === 'PUT' ? { ok: false, status: 409, json: async () => ({ mensaje: 'La receta fue modificada; recargala antes de guardar' }) } : response(recipe);
  });
  await act(async () => reactProps(button(container, 'Editar receta de Cheese')).onClick());
  const quantity = () => elements(container, (node) => node.localName === 'input' && reactProps(node).placeholder === 'Ej.: 0,25 o 1/4')[0];
  await change(quantity(), '1/4');
  assert.match(container.textContent, /0,25 g por producto/);
  await act(async () => reactProps(button(container, 'Guardar receta')).onClick());
  assert.equal(reactProps(quantity()).value, '1/4');
  assert.match(container.textContent, /La receta fue modificada/);
  assert.ok(button(container, 'Guardar receta'));
  await act(async () => reactProps(button(container, 'Volver a cargar receta')).onClick());
  assert.equal(reactProps(quantity()).value, '25');
});
