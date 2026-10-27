import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';
let server, dom, createRoot, Inventory, Catalog, AccessControl, UserRoleEditor, RolePermissionsEditor, NewUserForm, RecipeModal;
const previousFetch = globalThis.fetch;
const previousReader = globalThis.FileReader;
const user = { id: 1, backendRole: 'ADMINISTRADOR' };
const data = { state: { inventory: [], catalog: [{ id: 1, categoryId: 1, category: 'Burgers', name: 'Cheese', price: 100 }], inventoryStatus: 'ready', catalogStatus: 'ready' }, refreshInventory: async () => {}, refreshCatalog: async () => {} };
const find = (container, tag) => elements(container, (node) => node.localName === tag);
const button = (container, text) => find(container, 'button').find((node) => node.textContent.trim() === text || reactProps(node)['aria-label'] === text);
const change = async (node, value) => act(async () => reactProps(node).onChange({ target: { value } }));
before(async () => {
  dom = installMinimalDom(); ({ createRoot } = await import('react-dom/client'));
  globalThis.__validationArea = { user, data, successes: [] };
  server = await createTestServer({ configFile: false, plugins: [{ name: 'validation-area', enforce: 'pre', resolveId(source) { return source === 'sonner' ? '\0validation-toast' : null; }, load(id) {
    if (id === '\0validation-toast') return 'export const toast={error(){},success(...args){globalThis.__validationArea.successes.push(args)},info(){}};';
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'export const useAuth=()=>({user:globalThis.__validationArea.user,refreshSession:async()=>{}});';
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return 'export const useData=()=>globalThis.__validationArea.data;';
    return null;
  } }, react()], ssr: { noExternal: ['sonner'] }, server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Inventory } = await server.ssrLoadModule('/src/inventory/Inventory.jsx'));
  ({ default: Catalog } = await server.ssrLoadModule('/src/management/Catalog.jsx'));
  ({ default: NewUserForm } = await server.ssrLoadModule('/src/management/NewUserForm.jsx'));
  ({ default: RecipeModal } = await server.ssrLoadModule('/src/management/RecipeModal.jsx'));
  ({ default: AccessControl, UserRoleEditor, RolePermissionsEditor } = await server.ssrLoadModule('/src/management/AccessControl.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; globalThis.FileReader = previousReader; delete globalThis.__validationArea; await server?.close(); dom?.restore(); });
async function mount(t, Component, props = {}, captureRoot = () => {}) {
  globalThis.__validationArea.user = user;
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  captureRoot(root);
  await act(async () => root.render(createElement(MemoryRouter, null, createElement(Component, props))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
async function inventoryForm(t) {
  const container = await mount(t, Inventory);
  await act(async () => reactProps(button(container, 'Añadir Insumo')).onClick());
  const inputs = find(container, 'input');
  await change(inputs[0], ' Tomate '); await change(inputs[1], '0,125'); await change(inputs[2], '0,25');
  return container;
}
test('inventario normaliza decimales locales y bloquea dos altas dentro del mismo evento', async (t) => {
  const wait = deferred(); const sent = [];
  data.createIngredient = async (body) => { sent.push(body); return wait.promise; };
  const container = await inventoryForm(t); let first, second;
  await act(async () => { const submit = reactProps(find(container, 'form')[0]).onSubmit; first = submit({ preventDefault() {} }); second = submit({ preventDefault() {} }); });
  await act(async () => { wait.resolve({}); await Promise.all([first, second]); });
  assert.equal(sent.length, 1);
  assert.deepEqual(sent[0], { name: 'Tomate', unit: 'UNIDAD', stock: '0.125', min: '0.25' });
});
test('inventario rechaza blanco, negativo, umbral cero y exceso de precisión conservando el formulario', async (t) => {
  const sent = []; data.createIngredient = async (body) => { sent.push(body); };
  const container = await inventoryForm(t);
  for (const invalid of ['', '-1', 'NaN', '0,0001', '1000000000']) {
    await change(find(container, 'input')[1], invalid);
    await act(async () => reactProps(find(container, 'form')[0]).onSubmit({ preventDefault() {} }));
    assert.equal(sent.length, 0, invalid);
    assert.ok(find(container, 'form')[0]);
  }
  await change(find(container, 'input')[1], '0'); await change(find(container, 'input')[2], '0');
  await act(async () => reactProps(find(container, 'form')[0]).onSubmit({ preventDefault() {} })); assert.equal(sent.length, 0);
});
test('lectura de imagen no borra los campos editados mientras carga', async (t) => {
  let reader;
  globalThis.FileReader = class { constructor() { reader = this; } readAsDataURL() {} };
  const container = await mount(t, Catalog);
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  const file = find(container, 'input').find((node) => reactProps(node).type === 'file');
  await act(async () => reactProps(file).onChange({ target: { files: [{ type: 'image/png' }] } }));
  const name = find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-name');
  await change(name, 'Nueva burger');
  await act(async () => { reader.result = 'data:image/png;base64,YQ=='; (reader.onload || reader.onloadend)(); });
  assert.equal(reactProps(name).value, 'Nueva burger');
});
test('control de acceso no consulta usuarios ni permisos sin rol administrador', async (t) => {
  let calls = 0; globalThis.fetch = async () => { calls++; return { ok: true, json: async () => [] }; };
  const NonAdmin = () => { globalThis.__validationArea.user = { id: 4, backendRole: 'EMPLEADO' }; return createElement(AccessControl); };
  const container = await mount(t, NonAdmin);
  assert.match(container.textContent, /reservado al administrador/); assert.equal(calls, 0);
});
for (const kind of ['usuario', 'permisos']) test(`editor de ${kind} bloquea doble envío síncrono`, async (t) => {
  const wait = deferred(); let calls = 0; globalThis.fetch = async () => { calls++; return wait.promise; };
  const role = { rol: 'EMPLEADO', nombre: 'Empleado', permisos: [], disponibles: ['pedidos.ver'], version: 1, editable: true };
  const props = kind === 'usuario' ? { person: { id: 9, rol: 'CLIENTE', username: 'ana' }, roles: [role], onSaved() {} } : { role, modules: [{ clave: 'pedidos', nombre: 'Pedidos', acciones: [{ clave: 'ver', nombre: 'Ver' }] }], onSaved() {} };
  const container = await mount(t, kind === 'usuario' ? UserRoleEditor : RolePermissionsEditor, props);
  if (kind === 'usuario') await change(find(container, 'select')[0], 'EMPLEADO');
  else await act(async () => reactProps(find(container, 'input')[0]).onChange({ target: { checked: true } }));
  let first, second; await act(async () => { const submit = reactProps(find(container, 'form')[0]).onSubmit; first = submit({ preventDefault() {} }); second = submit({ preventDefault() {} }); });
  await act(async () => { wait.resolve({ ok: true, json: async () => kind === 'usuario' ? { id: 9, rol: 'EMPLEADO' } : role }); await Promise.all([first, second]); });
  assert.equal(calls, 1);
});
test('reposición bloquea dos clics simultáneos y permite reintentar un rechazo', async (t) => {
  data.state.inventory = [{ id: 12, name: 'Pan', category: 'UNIDAD', stock: 10, min: 1 }];
  const wait = deferred(); let calls = 0;
  data.replenishIngredient = async () => { calls++; return wait.promise; };
  t.after(() => { data.state.inventory = []; });
  const container = await mount(t, Inventory);
  let first, second;
  await act(async () => { const click = reactProps(button(container, 'Reponer una unidad de Pan')).onClick; first = click(); second = click(); });
  await act(async () => { wait.reject(Error('Stock no guardado')); await Promise.all([first, second]); });
  assert.equal(calls, 1);
  data.replenishIngredient = async () => { calls++; };
  await act(async () => reactProps(button(container, 'Reponer una unidad de Pan')).onClick());
  assert.equal(calls, 2);
});
test('catálogo rechaza nombre fuera de contrato e identifica el campo inválido', async (t) => {
  let calls = 0; data.createProduct = async () => { calls++; };
  const container = await mount(t, Catalog);
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  const name = find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-name');
  await change(name, 'x'.repeat(121));
  const price = find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-price');
  await change(price, '100');
  const ingredient = find(container, 'select').find((node) => node.getAttribute('id')?.includes('-ingredient-'));
  await change(ingredient, '12');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.equal(calls, 0);
  assert.equal(reactProps(name)['aria-invalid'], true);
  assert.match(container.textContent, /120/);
});
test('un archivo no imagen o ilegible muestra el error y conserva los datos', async (t) => {
  let reader; globalThis.FileReader = class { constructor() { reader = this; } readAsDataURL() {} };
  const container = await mount(t, Catalog);
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  const file = find(container, 'input').find((node) => reactProps(node).type === 'file');
  await act(async () => reactProps(file).onChange({ target: { files: [{ type: 'text/plain' }] } }));
  assert.equal(reader, undefined); assert.match(container.textContent, /archivo de imagen/);
  await act(async () => reactProps(file).onChange({ target: { files: [{ type: 'image/png' }] } }));
  await act(async () => reader.onerror());
  assert.match(container.textContent, /No se pudo leer la imagen/);
});
test('alta de usuario identifica campos inválidos y respeta política real de contraseña', async (t) => {
  let calls = 0; globalThis.fetch = async () => { calls++; return { ok: true, json: async () => ({}) }; };
  const container = await mount(t, NewUserForm, { roles: [{ rol: 'EMPLEADO', nombre: 'Empleado' }], onCreated() {} });
  for (const [name, value] of Object.entries({ nombre: 'Ana', apellido: 'Pérez', username: 'anaperez', password: '12345678' })) {
    await change(find(container, 'input').find((node) => reactProps(node).name === name), value);
  }
  await act(async () => reactProps(find(container, 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.equal(calls, 0);
  const password = find(container, 'input').find((node) => reactProps(node).name === 'password');
  assert.equal(reactProps(password)['aria-invalid'], true);
  assert.match(container.textContent, /solo números/);
});
test('receta no consulta el endpoint si la sesión no tiene permiso', async (t) => {
  let calls = 0; globalThis.fetch = async () => { calls++; return { ok: true, json: async () => ({ ingredientes: [], variantes: [] }) }; };
  const DeniedRecipe = () => { globalThis.__validationArea.user = { id: 5, backendRole: 'EMPLEADO', permisos: [] }; return createElement(RecipeModal, { product: { id: 1 }, onClose() {} }); };
  await mount(t, DeniedRecipe);
  assert.equal(calls, 0);
});
test('desactivar producto bloquea dos confirmaciones simultáneas', async (t) => {
  const wait = deferred(); let calls = 0; data.deactivateProduct = async () => { calls++; return wait.promise; };
  const container = await mount(t, Catalog);
  await act(async () => reactProps(find(container, 'button').find((node) => reactProps(node).title === 'Eliminar')).onClick());
  let first, second;
  await act(async () => { const click = reactProps(button(container, 'Sí')).onClick; first = click(); second = click(); });
  await act(async () => { wait.resolve(); await Promise.all([first, second]); });
  assert.equal(calls, 1);
});
test('ingrediente retirado durante alta se indica y no se envía una receta desactualizada', async (t) => {
  let calls = 0; data.createProduct = async () => { calls++; };
  data.state.inventory = [{ id: 12, name: 'Pan', category: 'UNIDAD' }];
  t.after(() => { data.state.inventory = []; });
  const container = await mount(t, Catalog);
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  await change(find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-name'), 'Nueva burger');
  await change(find(container, 'select').find((node) => node.getAttribute('id')?.includes('-ingredient-')), '12');
  data.state.inventory = [];
  await change(find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-price'), '100');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.equal(calls, 0);
  assert.match(container.textContent, /ingrediente.*disponible/i);
});
test('cantidades inválidas se asocian al campo al intentar guardar sin blur', async (t) => {
  const container = await mount(t, Catalog);
  data.state.inventory = [{ id: 12, name: 'Pan', category: 'UNIDAD' }];
  t.after(() => { data.state.inventory = []; });
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  await change(find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-name'), 'Nueva');
  await change(find(container, 'input').find((node) => node.getAttribute('id') === 'new-product-price'), '100');
  await change(find(container, 'select').find((node) => node.getAttribute('id')?.includes('-ingredient-')), '12');
  const quantity = find(container, 'input').find((node) => reactProps(node).placeholder === 'Ej.: 0,25 o 1/4');
  await change(quantity, '1/0');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.equal(reactProps(quantity)['aria-invalid'], true);
  assert.match(container.textContent, /denominador/);
});
test('variantes señalan nombre duplicado y precio inválido en sus campos', async (t) => {
  const container = await mount(t, Catalog);
  await act(async () => reactProps(button(container, 'Nuevo Producto')).onClick());
  await act(async () => reactProps(button(container, 'Usar variantes')).onClick());
  await act(async () => reactProps(button(container, 'Agregar variante')).onClick());
  const names = find(container, 'input').filter((node) => node.getAttribute('id')?.includes('-variant-'));
  await change(names[1], 'simple');
  await act(async () => reactProps(button(container, 'Guardar Producto')).onClick());
  assert.equal(reactProps(names[1])['aria-invalid'], true);
  const price = find(container, 'input').find((node) => node.getAttribute('id')?.endsWith('-price-1'));
  assert.equal(reactProps(price)['aria-invalid'], true);
});
test('alta de insumo no anuncia éxito a otra sesión después de desmontarse', async (t) => {
  let root; const wait = deferred(); data.createIngredient = async () => wait.promise;
  globalThis.__validationArea.successes = [];
  const container = await mount(t, Inventory, {}, (value) => { root = value; });
  await act(async () => reactProps(button(container, 'Añadir Insumo')).onClick());
  const inputs = find(container, 'input');
  await change(inputs[0], 'Pan'); await change(inputs[1], '1'); await change(inputs[2], '1');
  let saving; await act(async () => { saving = reactProps(find(container, 'form')[0]).onSubmit({ preventDefault() {} }); });
  await act(async () => root.unmount());
  await act(async () => { wait.resolve({}); await saving; });
  assert.equal(globalThis.__validationArea.successes.length, 0);
});
