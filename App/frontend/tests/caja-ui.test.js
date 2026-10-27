import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps } from './minimal-dom.js';

let server, dom, Caja, createRoot;
const originalFetch = globalThis.fetch;
const user = { id: 4, backendRole: 'EMPLEADO', permisos: ['caja.ver', 'caja.generar', 'caja.aprobar'] };
const consolidation = { fecha: '2026-10-26', turno: 'NOCHE', desde: '2026-10-26T20:00:00-03:00', hasta: '2026-10-27T02:00:00-03:00', total_efectivo: '50.00', total_billeteras: '20.00', total_devoluciones: '5.00', total_general: '69.00', total_propinas: '4.00', cantidad_pedidos: 2, cantidad_pagos: 3, pagos_pendientes_conciliacion: 1, desglose_metodos: [{ metodo_pago: 'EFECTIVO', total: '50.00', cantidad: 2 }] };
const record = { id: 31, fecha: '2026-10-26', turno: 'NOCHE', abierto_en: '2026-10-26T20:00:00-03:00', cerrado_en: '2026-10-27T02:01:00-03:00', total_efectivo: '100.00', total_billeteras: '45.00', total_devoluciones: '5.00', total_general: '140.00', cantidad_pedidos: 3, estado: 'PENDIENTE_APROBACION', generado_por: 4, aprobado_por: null, aprobado_en: null, observaciones: 'Nota previa' };
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const find = (node, tag) => elements(node, (child) => child.localName === tag);
const button = (node, text) => find(node, 'button').find((child) => child.textContent.trim() === text);
before(async () => {
  dom = installMinimalDom(); ({ createRoot } = await import('react-dom/client'));
  globalThis.__cajaAuth = { user, refreshSession: async () => {} };
  server = await createTestServer({ configFile: false, plugins: [{ name: 'caja-auth', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'export const useAuth=()=>globalThis.__cajaAuth;';
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', logLevel: 'silent' });
  ({ default: Caja } = await server.ssrLoadModule('/src/cash/Caja.jsx'));
});
after(async () => { globalThis.fetch = originalFetch; delete globalThis.__cajaAuth; await server?.close(); dom?.restore(); });
async function mount(t, currentUser = user) {
  globalThis.__cajaAuth.user = currentUser;
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  await act(async () => root.render(createElement(Caja)));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return { container, root };
}
test('render real muestra importes API, pendientes separados, detalle y confirmación', async (t) => {
  const writes = [];
  globalThis.fetch = async (path, opts = {}) => {
    if (opts.method === 'POST') { writes.push(JSON.parse(opts.body)); return response(record, 201); }
    return response(path.includes('consolidado') ? consolidation : path.endsWith('/31') ? record : [record]);
  };
  const { container } = await mount(t);
  assert.match(container.textContent, /69,00/); assert.match(container.textContent, /pendiente.*conciliación/i);
  assert.match(container.textContent, /26\/10\/2026/); assert.match(container.textContent, /arrastre/);
  await act(async () => reactProps(button(container, 'Generar cierre')).onClick());
  assert.match(container.textContent, /Recalcular cierre/); assert.match(container.textContent, /Nota previa/);
  const dialog = find(container, 'dialog')[0]; assert.equal(dialog.open, true);
  await act(async () => reactProps(button(container, 'Confirmar recálculo')).onClick());
  assert.equal(writes.length, 1); assert.equal(writes[0].observaciones, null);
  assert.match(container.textContent, /140,00/); assert.match(container.textContent, /Generación confirmada/);
});
test('sin autorización no consulta ni renderiza datos y cambio de usuario limpia privados', async (t) => {
  let calls = 0;
  globalThis.fetch = async (path) => { calls++; return response(path.includes('consolidado') ? consolidation : []); };
  const { container, root } = await mount(t, { ...user, permisos: [] });
  assert.equal(calls, 0); assert.doesNotMatch(container.textContent, /69,00/);
  globalThis.__cajaAuth.user = user; await act(async () => root.render(createElement(Caja)));
  assert.match(container.textContent, /69,00/);
  globalThis.__cajaAuth.user = null; await act(async () => root.render(createElement(Caja)));
  assert.doesNotMatch(container.textContent, /69,00|26\/10\/2026/);
});
test('403 retira datos y permisos separados no muestran acciones financieras', async (t) => {
  let revoked = false;
  globalThis.fetch = async (path) => response(revoked ? { detail: 'Revocado' } : path.includes('consolidado') ? consolidation : [], revoked ? 403 : 200);
  const { container } = await mount(t, { ...user, permisos: ['caja.ver'] });
  assert.equal(Boolean(button(container, 'Generar cierre')), false);
  revoked = true; await act(async () => reactProps(find(container, 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.doesNotMatch(container.textContent, /69,00/); assert.match(container.textContent, /rechazó el acceso/);
});
test('cierre conocido aprobado no ofrece generar ni recalcular', async (t) => {
  const approved = { ...record, estado: 'APROBADO', aprobado_por: 4, aprobado_en: '2026-10-27T03:00:00-03:00' };
  globalThis.fetch = async (path) => response(path.includes('consolidado') ? consolidation : [approved]);
  const { container } = await mount(t);
  assert.equal(Boolean(button(container, 'Generar cierre')), false);
});
