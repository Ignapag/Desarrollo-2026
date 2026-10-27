import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';
import { periodoInicial, validarFechas } from '../src/management/analyticsModel.js';

let server, dom, createRoot, Analytics, ControlPanel;
const originalFetch = globalThis.fetch;
const user = (id = 1, permisos = ['reportes.ver']) => ({ id, backendRole: 'EMPLEADO', permisos });
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const dashboard = (producto = 'Monu real') => ({ fecha_desde: '2026-10-01', fecha_hasta: '2026-10-22', ranking_productos: [{ producto_id: 1, producto, cantidad_vendida: 3, ranking: 1 }], ingreso_neto_confirmado: '90.25', ingresos_por_metodo: [{ metodo_pago: 'EFECTIVO', ingreso_neto: '90.25' }], pedidos_dia: 1, pedidos_semana: 2, pedidos_mes: 3, alertas_stock: [], actualizado_en: '2026-10-22T12:00:00Z' });
const ventas = [{ periodo: '2026-10-01', producto_id: 1, producto: 'Monu real', cantidad_vendida: 3, cantidad_pedidos: 1 }];
test('período inicial usa 30 días inclusivos y fecha argentina al cambiar el mes UTC', () => {
  assert.deepEqual(periodoInicial(new Date('2026-11-01T01:00:00Z')), { desde: '2026-10-02', hasta: '2026-10-31' });
  assert.equal(validarFechas({ desde: '2026-02-29', hasta: '2026-03-01' }), 'Completá ambas fechas con un día válido.');
  assert.equal(validarFechas({ desde: '2026-10-01', hasta: '2026-10-01' }), '');
});
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'analytics-boundaries', enforce: 'pre', resolveId(id) { if (id === 'recharts') return '\0charts-test'; }, load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'export const useAuth=()=>globalThis.__analyticsAuth;';
    if (id === '\0charts-test') return 'export const ResponsiveContainer=()=>null; export const AreaChart=()=>null; export const Area=()=>null; export const XAxis=()=>null; export const YAxis=()=>null; export const CartesianGrid=()=>null; export const Tooltip=()=>null;';
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Analytics } = await server.ssrLoadModule('/src/management/Analytics.jsx'));
  ({ default: ControlPanel } = await server.ssrLoadModule('/src/management/ControlPanel.jsx'));
});
after(async () => { globalThis.fetch = originalFetch; delete globalThis.__analyticsAuth; await server?.close(); dom?.restore(); });
async function mount(t, identity = user(), Component = Analytics) {
  globalThis.__analyticsAuth = { user: identity, refreshSession() {} };
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const render = async (identity) => {
    if (identity !== undefined) globalThis.__analyticsAuth.user = identity;
    await act(async () => root.render(createElement(MemoryRouter, null, createElement(Component))));
  };
  await render();
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return { container, render };
}
const find = (container, tag, text) => elements(container, (node) => node.localName === tag && (!text || node.textContent.includes(text)))[0];
async function change(container, field, value) {
  const input = elements(container, (node) => node.localName === 'input' && reactProps(node).name === field)[0];
  assert.ok(input, `Existe campo ${field}`);
  await act(async () => reactProps(input).onChange({ target: { value } }));
}
async function submit(container) { await act(async () => reactProps(find(container, 'form')).onSubmit({ preventDefault() {} })); }
function serve(calls, overrides = {}) {
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    if (path.includes('/dashboard')) return response(overrides.dashboard ?? dashboard());
    if (path.includes('/rentabilidad')) return response(overrides.rentabilidad ?? []);
    return response(overrides.ventas ?? ventas);
  };
}

test('consulta contratos reales, separa unidades de pedidos y no pide ni muestra finanzas sin permiso', async (t) => {
  const calls = []; serve(calls);
  const { container } = await mount(t);
  assert.equal(calls.length, 2);
  assert.ok(calls.some(({ path }) => path.includes('/ventas?') && path.includes('agrupacion=DIA')));
  assert.match(container.textContent, /Monu real/);
  assert.match(container.textContent, /Pedidos con este producto/);
  assert.doesNotMatch(container.textContent, /90,25|Cobros netos|Rentabilidad estimada|Importe vendido/);
  assert.ok(elements(container, (node) => node.localName === 'table').length >= 2);
});

test('el año cero no pertenece al contrato date del backend', () => {
  assert.notEqual(validarFechas({ desde: '0000-01-01', hasta: '0000-01-02' }), '');
});

test('panel retira métricas de otro usuario con el mismo rol durante la carga', async (t) => {
  serve([], { dashboard: dashboard('Privado de la primera sesión') });
  const { container, render } = await mount(t, user(), ControlPanel);
  assert.match(container.textContent, /Privado de la primera sesión/);
  const waits = [deferred(), deferred()]; let index = 0;
  globalThis.fetch = () => waits[index++].promise;
  await render(user(2));
  assert.doesNotMatch(container.textContent, /Privado de la primera sesión/);
  assert.match(container.textContent, /Cargando métricas/);
  await act(async () => { waits[0].resolve(response(dashboard('Segunda sesión'))); waits[1].resolve(response([])); });
  assert.match(container.textContent, /Segunda sesión/);
});

test('panel no conserva datos ni errores de autorización al cambiar la sesión', async (t) => {
  serve([]);
  const { container, render } = await mount(t, user(), ControlPanel);
  let refreshed = 0;
  globalThis.__analyticsAuth.refreshSession = () => { refreshed += 1; };
  globalThis.fetch = async () => response({ detail: 'Permiso retirado' }, 403);
  await act(async () => reactProps(find(container, 'button', 'Actualizar')).onClick());
  assert.doesNotMatch(container.textContent, /Monu real/);
  assert.equal(refreshed, 1);
  const waits = [deferred(), deferred()]; let index = 0;
  globalThis.fetch = () => waits[index++].promise;
  await render(user(2));
  assert.doesNotMatch(container.textContent, /Permiso retirado/);
  await act(async () => { waits[0].resolve(response(dashboard())); waits[1].resolve(response([])); });
});

test('panel conserva datos recuperables ante 503 y descarta respuestas de una sesión anterior', async (t) => {
  serve([], { dashboard: dashboard('Métricas recuperables') });
  const { container, render } = await mount(t, user(), ControlPanel);
  globalThis.fetch = async () => response({ detail: 'Temporalmente fuera de servicio' }, 503);
  await act(async () => reactProps(find(container, 'button', 'Actualizar')).onClick());
  assert.match(container.textContent, /Métricas recuperables/);
  assert.match(container.textContent, /Se muestran los últimos datos recibidos/);
  const waits = [deferred(), deferred()]; let index = 0;
  globalThis.fetch = () => waits[index++].promise;
  await act(async () => reactProps(find(container, 'button', 'Reintentar')).onClick());
  serve([], { dashboard: dashboard('Métricas vigentes') });
  await render(user(2));
  await act(async () => { waits[0].resolve(response(dashboard('Respuesta obsoleta'))); waits[1].resolve(response([])); });
  assert.match(container.textContent, /Métricas vigentes/);
  assert.doesNotMatch(container.textContent, /Respuesta obsoleta|Métricas recuperables/);
});

test('reportes no consulta al usuario sin autorización, incluido logout', async (t) => {
  const calls = []; serve(calls);
  const { container, render } = await mount(t, user(1, []));
  assert.equal(calls.length, 0);
  assert.match(container.textContent, /No tenés permiso/);
  await render(null);
  assert.equal(calls.length, 0);
});

for (const status of [400, 401, 403, 409, 422, 429, 500]) {
  test(`reportes informa HTTP ${status} sin inventar resultados y permite reintentar`, async (t) => {
    globalThis.fetch = async () => response({ detail: `Error HTTP ${status}` }, status);
    const { container } = await mount(t);
    assert.match(container.textContent, new RegExp(`Error HTTP ${status}`));
    assert.doesNotMatch(container.textContent, /Monu real|No hay ventas confirmadas/);
    serve([]);
    await act(async () => reactProps(find(container, 'button', 'Reintentar')).onClick());
    assert.match(container.textContent, /Monu real/);
  });
}

test('reportes informa desconexión y respuesta no JSON sin presentar datos vacíos', async (t) => {
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
  const { container } = await mount(t);
  assert.match(container.textContent, /No se pudo conectar/);
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('HTML'); } });
  await act(async () => reactProps(find(container, 'button', 'Reintentar')).onClick());
  assert.match(container.textContent, /no devolvió una respuesta válida/);
  assert.doesNotMatch(container.textContent, /No hay ventas confirmadas|Monu real/);
});
test('fechas inválidas no consultan y editar oculta inmediatamente los resultados anteriores', async (t) => {
  const calls = []; serve(calls);
  const { container } = await mount(t);
  await change(container, 'desde', '2026-10-23');
  await change(container, 'hasta', '2026-10-01');
  assert.doesNotMatch(container.textContent, /Monu real/);
  await submit(container);
  assert.equal(calls.length, 2);
  assert.match(container.textContent, /anterior o igual/);
  assert.equal(document.activeElement.getAttribute('id'), 'error-periodo');
  await change(container, 'desde', ''); await submit(container);
  assert.equal(calls.length, 2);
  assert.match(container.textContent, /Completá/);
  await change(container, 'desde', '2026-09-01');
  await submit(container);
  assert.equal(calls.length, 4);
  assert.ok(calls[2].path.includes('fecha_desde=2026-09-01&fecha_hasta=2026-10-01'));
});
test('error del período oculta datos, permite reintentar y un período vacío no inventa ventas', async (t) => {
  const calls = []; serve(calls);
  const { container } = await mount(t);
  globalThis.fetch = async () => response({ detail: 'Servicio no disponible' }, 503);
  await submit(container);
  assert.match(container.textContent, /Servicio no disponible/);
  assert.doesNotMatch(container.textContent, /Monu real/);
  serve(calls, { dashboard: { ...dashboard(), ranking_productos: [] }, ventas: [] });
  await act(async () => reactProps(find(container, 'button', 'Reintentar')).onClick());
  assert.match(container.textContent, /No hay ventas confirmadas/);
  assert.doesNotMatch(container.textContent, /Monu real|Servicio no disponible/);
});
test('respuestas atrasadas no pisan un filtro nuevo aunque fetch ignore abort', async (t) => {
  const waits = [deferred(), deferred()]; let index = 0;
  globalThis.fetch = () => waits[index++].promise;
  const { container } = await mount(t);
  assert.match(container.textContent, /Cargando/);
  const calls = []; serve(calls, { dashboard: dashboard('Período nuevo') });
  await change(container, 'desde', '2026-09-01'); await submit(container);
  assert.match(container.textContent, /Período nuevo/);
  await act(async () => { waits[0].resolve(response(dashboard('Período viejo'))); waits[1].resolve(response(ventas)); });
  assert.match(container.textContent, /Período nuevo/);
  assert.doesNotMatch(container.textContent, /Período viejo/);
});
test('cambio de sesión con el mismo rol descarta respuestas y datos previos', async (t) => {
  const waits = [deferred(), deferred()]; let index = 0;
  globalThis.fetch = () => waits[index++].promise;
  const { container, render } = await mount(t);
  serve([], { dashboard: dashboard('Otra sesión') });
  await render(user(2));
  await act(async () => { waits[0].resolve(response(dashboard('Sesión anterior'))); waits[1].resolve(response(ventas)); });
  assert.match(container.textContent, /Otra sesión/);
  assert.doesNotMatch(container.textContent, /Sesión anterior/);
  await render(user(3, []));
  assert.match(container.textContent, /No tenés permiso/);
  assert.doesNotMatch(container.textContent, /Otra sesión/);
});
test('finanzas requieren ambos permisos y se retiran al revocar autorización', async (t) => {
  const calls = []; serve(calls, { ventas: [{ ...ventas[0], monto_total: '120.50', participacion: '100', cantidad_pedidos: undefined }], rentabilidad: [{ producto_id: 1, producto: 'Monu real', unidades_vendidas: 3, ingreso_estimado: '120.50', costo_estimado: '50', margen_estimado: '70.50', porcentaje_margen: '58.506' }] });
  const { container, render } = await mount(t, user(1, ['reportes.ver', 'reportes.financieros']));
  assert.equal(calls.length, 3);
  assert.match(container.textContent, /Cobros netos/);
  assert.match(container.textContent, /Rentabilidad estimada/);
  assert.match(container.textContent, /90,25/);
  assert.doesNotMatch(container.textContent, /Pedidos con este producto/);
  serve(calls);
  await render(user(1));
  assert.equal(calls.length, 5);
  assert.doesNotMatch(container.textContent, /Cobros netos|Rentabilidad estimada|90,25/);
  await render(user(1, ['reportes.financieros']));
  assert.equal(calls.length, 5);
  assert.match(container.textContent, /No tenés permiso/);
});

test('pedidos se agregan por producto a través de días sin inventar un total único', async (t) => {
  serve([], { dashboard: { ...dashboard(), ranking_productos: [
    { producto_id: 1, producto: 'Monu real', cantidad_vendida: 5, ranking: 1 },
    { producto_id: 2, producto: 'Papas', cantidad_vendida: 4, ranking: 2 },
  ] }, ventas: [
    { ...ventas[0], cantidad_vendida: 2 },
    { ...ventas[0], periodo: '2026-10-02', cantidad_vendida: 3 },
    { ...ventas[0], producto_id: 2, producto: 'Papas', cantidad_vendida: 4 },
  ] });
  const { container } = await mount(t);
  const ranking = elements(container, (node) => node.localName === 'table' && node.textContent.includes('Pedidos con este producto'))[0];
  const filas = elements(ranking, (node) => node.localName === 'tbody')[0].childNodes;
  assert.deepEqual(filas.map((fila) => fila.childNodes.slice(1).map((celda) => celda.textContent)), [['5', '2'], ['4', '1']]);
  const diaria = elements(container, (node) => node.localName === 'table' && node.textContent.includes('Unidades vendidas por día'))[0];
  assert.match(diaria.textContent, /01\/10\/20266.*02\/10\/20263/);
  assert.doesNotMatch(container.textContent, /Total de pedidos|Pedidos únicos: 3/);
});

test('revocar finanzas durante la carga descarta también sus respuestas tardías', async (t) => {
  const waits = [deferred(), deferred(), deferred()]; let index = 0;
  globalThis.fetch = () => waits[index++].promise;
  const { container, render } = await mount(t, user(1, ['reportes.ver', 'reportes.financieros']));
  serve([]);
  await render(user(1));
  await act(async () => {
    waits[0].resolve(response(dashboard('Finanzas revocadas')));
    waits[1].resolve(response([{ ...ventas[0], monto_total: '120.50' }]));
    waits[2].resolve(response([]));
  });
  assert.match(container.textContent, /Monu real/);
  assert.doesNotMatch(container.textContent, /Finanzas revocadas|Rentabilidad estimada|Cobros netos|120,50/);
});
