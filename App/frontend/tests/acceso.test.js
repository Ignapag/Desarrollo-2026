import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createTestServer as createServer } from './vite-test-server.js';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';
import { can, canVisit } from '../src/auth/permissions.js';
let server, dom, createRoot, editors, NewUserForm;
const previousFetch = globalThis.fetch;
const employee = { rol: 'EMPLEADO', nombre: 'Empleado', editable: true, version: 3, permisos: ['pedidos.ver'], disponibles: ['pedidos.ver', 'pedidos.editar'] };
const modules = [{ clave: 'pedidos', nombre: 'Pedidos', acciones: [{ clave: 'ver', nombre: 'Ver pedidos' }, { clave: 'editar', nombre: 'Editar pedidos' }, { clave: 'crear', nombre: 'Crear pedidos' }] }];
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, plugins: [react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  editors = await server.ssrLoadModule('/src/management/AccessControl.jsx');
  ({ default: NewUserForm } = await server.ssrLoadModule('/src/management/NewUserForm.jsx'));
});
after(async () => { globalThis.fetch = previousFetch; await server?.close(); dom?.restore(); });
async function mount(t, component, props) {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(component, props)));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
test('el rol legacy admin no concede permisos ni acceso a administración', () => {
  const user = { backendRole: 'EMPLEADO', role: 'admin', permisos: ['pedidos.ver'] };
  assert.equal(canVisit(user, '/dashboard/access'), false);
  assert.equal(canVisit(user, '/dashboard/orders'), true);
  assert.equal(canVisit(user, '/dashboard/inventory'), false);
  assert.equal(can(user, 'usuarios.administrar_permisos'), false);
  assert.equal(canVisit({ backendRole: 'ADMINISTRADOR' }, '/dashboard/access'), true);
  assert.equal(canVisit({ backendRole: 'REPARTIDOR', permisos: ['delivery.ver'] }, '/delivery'), true);
});
test('matriz usa acciones API, conserva roles protegidos y limita permisos disponibles', () => {
  const html = renderToStaticMarkup(createElement(editors.RolePermissionsEditor, { role: employee, modules }));
  assert.match(html, /Ver pedidos/); assert.match(html, /No disponible para este rol/);
  assert.doesNotMatch(html, /scroll|overflow-x|usuarios/);
  const protectedHtml = renderToStaticMarkup(createElement(editors.RolePermissionsEditor, { role: { ...employee, rol: 'ADMINISTRADOR', editable: false }, modules }));
  assert.match(protectedHtml, /Protegido/); assert.doesNotMatch(protectedHtml, /Guardar permisos/);
});
test('guardar permisos envía versión, muestra pendiente y jamás confirma un error', async (t) => {
  let payload; const wait = deferred(); const saved = [];
  globalThis.fetch = async (_path, options) => { payload = JSON.parse(options.body); return wait.promise; };
  const container = await mount(t, editors.RolePermissionsEditor, { role: employee, modules, onSaved: (role) => saved.push(role) });
  const inputs = elements(container, (node) => node.localName === 'input');
  await act(async () => reactProps(inputs[1]).onChange({ target: { checked: true } }));
  let pending;
  await act(async () => { pending = reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); });
  assert.deepEqual(payload, { permisos: ['pedidos.ver', 'pedidos.editar'], version: 3 });
  assert.match(container.textContent, /Guardando/);
  await act(async () => { wait.resolve(response({ detail: 'No disponible' }, 500)); await pending; });
  assert.equal(saved.length, 0); assert.match(container.textContent, /No disponible/); assert.doesNotMatch(container.textContent, /Permisos guardados/);
});
test('conflicto bloquea reescritura y ofrece actualizar el rol', async (t) => {
  globalThis.fetch = async () => response({ detail: 'Conflicto' }, 409);
  const container = await mount(t, editors.RolePermissionsEditor, { role: employee, modules });
  await act(async () => reactProps(elements(container, (node) => node.localName === 'input')[1]).onChange({ target: { checked: true } }));
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.match(container.textContent, /Tus cambios no se guardaron/);
  assert.match(container.textContent, /Actualizar permisos del rol/);
  assert.equal(elements(container, (node) => node.localName === 'button' && node.textContent === 'Guardar permisos')[0].disabled, true);
});
test('asignar rol persiste usuario real por ID y sólo publica respuesta confirmada', async (t) => {
  let called;
  const person = { id: 19, nombre: 'Ana', apellido: 'Pérez', username: 'ana', rol: 'CLIENTE', estado: 'ACTIVO' };
  let saved;
  globalThis.fetch = async (path, options) => { called = { path, body: JSON.parse(options.body), method: options.method }; return response({ ...person, rol: 'EMPLEADO' }); };
  const container = await mount(t, editors.UserRoleEditor, { person, roles: [employee, { rol: 'CLIENTE', nombre: 'Cliente' }], onSaved: (value) => { saved = value; } });
  await act(async () => reactProps(elements(container, (node) => node.localName === 'select')[0]).onChange({ target: { value: 'EMPLEADO' } }));
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.deepEqual(called, { path: '/api/usuarios/19/rol', body: { rol: 'EMPLEADO' }, method: 'POST' });
  assert.equal(saved.id, 19); assert.equal(saved.rol, 'EMPLEADO');
});

test('ruta directa de acceso rechaza empleado y navegación omite módulos revocados', async (t) => {
  const scoped = await createServer({ configFile: false, plugins: [{ name: 'sesion-acceso-test', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "const user={id:4,name:'Operador',role:'admin',backendRole:'EMPLEADO',permisos:['pedidos.ver']}; export const useAuth=()=>({user,loading:false,logout(){}});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  t.after(() => scoped.close());
  const { MemoryRouter } = await import('react-router-dom');
  const { default: ProtectedRoute } = await scoped.ssrLoadModule('/src/auth/ProtectedRoute.jsx');
  const { default: Layout } = await scoped.ssrLoadModule('/src/management/DashboardLayout.jsx');
  const denied = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ProtectedRoute, { path: '/dashboard/access' }, 'Contenido privado')));
  assert.match(denied, /Sin acceso a esta sección/); assert.doesNotMatch(denied, /Contenido privado/);
  const nav = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Layout)));
  assert.match(nav, /href="\/dashboard\/orders"/);
  assert.doesNotMatch(nav, /href="\/dashboard\/access"|href="\/dashboard\/inventory"|href="\/dashboard\/customers"/);
});

test('repartidor respeta permisos configurados y catálogo de consulta no requiere gestionar', () => {
  assert.equal(canVisit({ backendRole: 'REPARTIDOR', permisos: [] }, '/delivery'), false);
  assert.equal(canVisit({ backendRole: 'REPARTIDOR', permisos: ['stock.ver'] }, '/dashboard/inventory'), true);
  assert.equal(canVisit({ backendRole: 'EMPLEADO', permisos: ['productos.ver_receta'] }, '/dashboard/catalog'), true);
});

async function fillNewUser(container) {
  const values = { nombre: 'Ana', apellido: 'Pérez', username: 'anaperez', password: 'MonuCuenta2026!' };
  for (const [name, value] of Object.entries(values)) {
    const input = elements(container, (node) => node.localName === 'input' && reactProps(node).name === name)[0];
    await act(async () => reactProps(input).onChange({ target: { value } }));
  }
}

test('crear cuenta envía credenciales y rol, agrega sólo la cuenta confirmada y borra contraseña', async (t) => {
  const pending = deferred(); let called; const created = [];
  globalThis.fetch = async (path, options) => { called = { path, body: JSON.parse(options.body), method: options.method }; return pending.promise; };
  const container = await mount(t, NewUserForm, { roles: [employee, { rol: 'REPARTIDOR', nombre: 'Repartidor' }], onCreated: (person) => created.push(person) });
  await fillNewUser(container);
  await act(async () => reactProps(elements(container, (node) => node.localName === 'select')[0]).onChange({ target: { value: 'REPARTIDOR' } }));
  let saving;
  await act(async () => { saving = reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); });
  assert.deepEqual(called, { path: '/api/usuarios', method: 'POST', body: { nombre: 'Ana', apellido: 'Pérez', username: 'anaperez', password: 'MonuCuenta2026!', rol: 'REPARTIDOR' } });
  assert.equal(created.length, 0);
  assert.match(container.textContent, /Creando/);
  await act(async () => { pending.resolve(response({ id: 24, nombre: 'Ana', apellido: 'Pérez', username: 'anaperez', rol: 'REPARTIDOR', estado: 'ACTIVO' }, 201)); await saving; });
  assert.equal(created[0].id, 24);
  const password = elements(container, (node) => node.localName === 'input' && reactProps(node).name === 'password')[0];
  assert.equal(password.value, '');
  assert.match(container.textContent, /Cuenta creada/);
  assert.doesNotMatch(container.textContent, /MonuCuenta2026!/);
});

test('alta rechazada conserva los datos y no agrega una cuenta ficticia', async (t) => {
  const created = [];
  globalThis.fetch = async () => response({ mensaje: 'Ese nombre de usuario ya existe' }, 409);
  const container = await mount(t, NewUserForm, { roles: [employee], onCreated: (person) => created.push(person) });
  await fillNewUser(container);
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.equal(created.length, 0);
  assert.match(container.textContent, /Ese nombre de usuario ya existe/);
  assert.equal(elements(container, (node) => node.localName === 'input' && reactProps(node).name === 'username')[0].value, 'anaperez');
  assert.doesNotMatch(container.textContent, /Cuenta creada/);
});

test('alta confirmada se incorpora al listado real y actualiza su contador', async (t) => {
  const scoped = await createServer({ configFile: false, plugins: [{ name: 'admin-cuentas-test', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "const user={id:1,backendRole:'ADMINISTRADOR',permisos:[]}; export const useAuth=()=>({user,refreshSession(){}});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  t.after(() => scoped.close());
  const { default: AccessControl } = await scoped.ssrLoadModule('/src/management/AccessControl.jsx');
  const created = { id: 24, nombre: 'Ana', apellido: 'Pérez', username: 'anaperez', rol: 'EMPLEADO', estado: 'ACTIVO' };
  const pending = deferred();
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'POST') return pending.promise;
    return response(path === '/api/acceso' ? { modulos: modules, roles: [employee] } : [{ id: 8, nombre: 'Cuenta', apellido: 'Anterior', username: 'anterior', rol: 'EMPLEADO', estado: 'ACTIVO' }]);
  };
  const container = await mount(t, AccessControl, {});
  assert.match(container.textContent, /1 usuarios/);
  await act(async () => reactProps(elements(container, (node) => node.localName === 'button' && node.textContent === 'Crear cuenta')[0]).onClick());
  await fillNewUser(container);
  let saving;
  await act(async () => { saving = reactProps(elements(container, (node) => node.localName === 'form' && reactProps(node)['aria-labelledby'] === 'nueva-cuenta-titulo')[0]).onSubmit({ preventDefault() {} }); });
  assert.equal(elements(container, (node) => node.localName === 'button' && node.textContent === 'Cerrar formulario')[0].disabled, true);
  await act(async () => { pending.resolve(response(created, 201)); await saving; });
  assert.match(container.textContent, /2 usuarios/);
  assert.match(container.textContent, /Ana Pérez/);
  assert.match(container.textContent, /anaperez · ACTIVO/);
});

test('alta con JSON incompleto conserva contraseña y no anuncia una cuenta creada', async (t) => {
  let created = 0;
  globalThis.fetch = async () => response({});
  const container = await mount(t, NewUserForm, { roles: [employee], onCreated: () => created++ });
  await fillNewUser(container);
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.equal(created, 0);
  assert.equal(elements(container, (node) => node.localName === 'input' && reactProps(node).name === 'password')[0].value, 'MonuCuenta2026!');
  assert.match(container.textContent, /confirmar|respuesta/);
});
test('roles y permisos con JSON incompleto no anuncian cambios guardados', async (t) => {
  globalThis.fetch = async () => response({});
  let saved = 0;
  const container = await mount(t, editors.UserRoleEditor, { person: { id: 19, rol: 'REPARTIDOR' }, roles: [employee, { rol: 'REPARTIDOR' }], onSaved: () => saved++ });
  await act(async () => reactProps(elements(container, (node) => node.localName === 'select')[0]).onChange({ target: { value: 'EMPLEADO' } }));
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.equal(saved, 0);
  assert.match(container.textContent, /confirmar|respuesta/);
  const role = await mount(t, editors.RolePermissionsEditor, { role: employee, modules, onSaved: () => saved++ });
  await act(async () => reactProps(elements(role, (node) => node.localName === 'input')[1]).onChange({ target: { checked: true } }));
  await act(async () => reactProps(elements(role, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.equal(saved, 0);
  assert.match(role.textContent, /confirmar|respuesta/);
});
