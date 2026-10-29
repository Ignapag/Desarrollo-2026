import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps } from './minimal-dom.js';

let dom, server, createRoot, Catalog, DataProvider;
const previousFetch = globalThis.fetch;
const detail = { producto_id: 1, nombre: 'Cheese', descripcion: 'Original', categoria_id: 1, categoria: 'Burgers', precio_base: '10000', imagen_url: '/cheese.png', activo: true, orden: 2, actualizado_en: '2026-10-29T12:00:00Z', categorias: [{ id: 1, nombre: 'Burgers', activa: true }, { id: 2, nombre: 'Combos', activa: true }], ingredientes: [{ ingrediente_id: 10, nombre: 'Queso', unidad_medida: 'GR', cantidad_requerida: '25', es_base: false }], variantes: [], extras: [] };
const catalogProduct = { id: 1, categoria_id: 1, categoria: 'Burgers', nombre: 'Cheese', precio_base: '10000', activo: true, disponible: true, variantes: [] };
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const button = (container, name) => elements(container, (node) => node.localName === 'button' && (node.textContent.trim() === name || reactProps(node)['aria-label'] === name))[0];
const field = (container, id) => elements(container, (node) => node.getAttribute?.('id') === id)[0];
const change = (node, value) => act(async () => reactProps(node).onChange({ target: { value } }));

before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'editor-auth', enforce: 'pre', resolveId(source) { return source === 'sonner' ? '\0editor-toast' : null; }, load(id) {
    if (id === '\0editor-toast') return 'export const toast={error(){},success(){},info(){}}';
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "const user={id:1,role:'admin',backendRole:'ADMINISTRADOR'}; export const useAuth=()=>({user});";
    return null;
  } }, react()], ssr: { noExternal: ['sonner'] }, server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Catalog } = await server.ssrLoadModule('/src/management/Catalog.jsx'));
  ({ DataProvider } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });
async function mount(t, extraFetch) {
  globalThis.fetch = async (path, options = {}) => extraFetch?.(path, options) || response(path === '/api/productos' ? [catalogProduct] : path === '/api/productos/1' ? detail : path.startsWith('/api/stock/ingredientes') ? [{ id: 10, nombre: 'Queso', unidad_medida: 'GR', cantidad_actual: '100', nivel: 'NORMAL' }] : []);
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(MemoryRouter, null, createElement(DataProvider, null, createElement(Catalog)))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}

test('edita un producto existente con metadatos, receta y versión en un único PUT', async (t) => {
  let sent, writes = 0;
  const container = await mount(t, (path, options) => {
    if (path === '/api/productos/1' && options.method === 'PUT') { sent = JSON.parse(options.body); writes += 1; return response({ ...detail, nombre: sent.nombre, precio_base: sent.precio_base, actualizado_en: '2026-10-29T13:00:00Z' }); }
  });
  assert.ok(button(container, 'Editar producto Cheese'));
  await act(async () => reactProps(button(container, 'Editar producto Cheese')).onClick());
  await change(field(container, 'edit-product-name'), 'Cheese renovada');
  await change(field(container, 'edit-product-price'), '12000,50');
  await change(field(container, 'edit-product-description'), 'Nueva receta');
  await change(field(container, 'edit-product-category'), '2');
  await act(async () => reactProps(button(container, 'Guardar producto')).onClick());
  assert.equal(writes, 1);
  assert.equal(sent.nombre, 'Cheese renovada');
  assert.equal(sent.precio_base, '12000.50');
  assert.equal(sent.categoria_id, 2);
  assert.equal(sent.descripcion, 'Nueva receta');
  assert.equal(sent.actualizado_en_esperado, detail.actualizado_en);
  assert.deepEqual(sent.ingredientes, [{ ingrediente_id: 10, cantidad_requerida: '25', es_base: false }]);
});
test('quitar imagen envía null y un conflicto conserva el borrador hasta recargar', async (t) => {
  let sent, loads = 0;
  const container = await mount(t, (path, options) => {
    if (path !== '/api/productos/1') return;
    if (options.method === 'PUT') { sent = JSON.parse(options.body); return response({ mensaje: 'El producto fue modificado; recargalo' }, 409); }
    loads += 1; return response(detail);
  });
  await act(async () => reactProps(button(container, 'Editar producto Cheese')).onClick());
  await change(field(container, 'edit-product-name'), 'Mi borrador');
  await act(async () => reactProps(button(container, 'Quitar imagen del producto')).onClick());
  await act(async () => reactProps(button(container, 'Guardar producto')).onClick());
  assert.equal(sent.imagen_url, null);
  assert.equal(reactProps(field(container, 'edit-product-name')).value, 'Mi borrador');
  assert.match(container.textContent, /cambió|cambio|información/);
  await act(async () => reactProps(button(container, 'Volver a cargar producto')).onClick());
  assert.equal(loads, 2);
  assert.equal(reactProps(field(container, 'edit-product-name')).value, 'Cheese');
});
test('no guarda datos inválidos y ofrece corregirlos dentro del formulario', async (t) => {
  let writes = 0;
  const container = await mount(t, (path, options) => { if (options.method === 'PUT') writes += 1; });
  await act(async () => reactProps(button(container, 'Editar producto Cheese')).onClick());
  await change(field(container, 'edit-product-name'), '   ');
  await act(async () => reactProps(button(container, 'Guardar producto')).onClick());
  assert.equal(writes, 0);
  assert.match(container.textContent, /nombre/);
  assert.equal(reactProps(field(container, 'edit-product-name')).value, '   ');
});
test('también ofrece editar productos activos ocultos por su categoría inactiva', async (t) => {
  const hidden = { ...catalogProduct, id: 22, nombre: 'Oculto por categoría', categoria_id: 4, categoria: 'Categoría inactiva' };
  const container = await mount(t, (path) => {
    if (path === '/api/productos?solo_activos=false') return response([catalogProduct, hidden]);
    if (path === '/api/productos/22') return response({ ...detail, producto_id: 22, nombre: hidden.nombre, categoria_id: 4, categorias: [{ id: 4, nombre: hidden.categoria, activa: false }] });
  });
  await act(async () => reactProps(button(container, 'Productos inactivos')).onClick());
  assert.ok(button(container, 'Editar producto Oculto por categoría'));
  assert.equal(button(container, 'Reactivar Oculto por categoría'), undefined);
  await act(async () => reactProps(button(container, 'Editar producto Oculto por categoría')).onClick());
  assert.equal(reactProps(field(container, 'edit-product-name')).value, hidden.nombre);
});
