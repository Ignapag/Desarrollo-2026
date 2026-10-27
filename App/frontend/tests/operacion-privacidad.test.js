import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps } from './minimal-dom.js';

let dom, server, createRoot, Orders, DeliveryPanel, OrderDetail, auth;
const originalFetch = globalThis.fetch;
const order = { id: 481, numero: 48, version: 1, estado: 'PENDIENTE', tipo_entrega: 'DELIVERY', cliente: 'Cliente privado', direccion: { calle: 'Domicilio privado', numero: '10', localidad: 'Ensenada' }, metodo_pago_acordado: 'EFECTIVO', total: '1000', saldo_pendiente: '1000', neto_cobrado: '0', items: [], pagos: [], historial: [] };
const trip = { id: 1, estado: 'PLANIFICADO', repartidor_nombre: 'Rider', envios: [{ id: 2, pedido_id: 481, numero: 48, estado: 'ASIGNADO', cliente_nombre: 'Cliente privado', calle: 'Domicilio privado', total: '1000', saldo_pendiente: '1000' }] };
const response = (value, status = 200) => ({ ok: status < 400, status, json: async () => value });
before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'private-operation-context', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return `export let refreshes=0; const refreshSession=async()=>{refreshes+=1;}; const user={id:1,backendRole:'EMPLEADO',permisos:['pedidos.ver','pedidos.editar','delivery.ver','delivery.operar']}; export const useAuth=()=>({user,refreshSession,logout:async()=>{}});`;
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return `const state={orders:[],ordersStatus:'ready'}; export const useData=()=>({state,watchOrders(){},orderOperationPending:()=>false,projectOrder:(order)=>order,runOrderMutation:async(op)=>op()});`;
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Orders } = await server.ssrLoadModule('/src/fulfillment/Orders.jsx'));
  ({ default: DeliveryPanel } = await server.ssrLoadModule('/src/fulfillment/DeliveryPanel.jsx'));
  ({ default: OrderDetail } = await server.ssrLoadModule('/src/fulfillment/OrderDetail.jsx'));
  auth = await server.ssrLoadModule('/src/auth/AuthContext.jsx');
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });
async function mount(t, Component, props = {}) {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(MemoryRouter, { initialEntries: ['/dashboard/orders?q=481'] }, createElement(Component, props))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
const button = (container, text) => elements(container, (node) => node.localName === 'button' && node.textContent === text)[0];
const settleSearch = () => act(async () => new Promise((resolve) => setTimeout(resolve, 300)));

for (const status of [401, 403, 503]) {
  for (const [ComponentName, label] of [['Orders', 'Actualizar pedidos'], ['DeliveryPanel', 'Actualizar viajes'], ['OrderDetail', 'Actualizar detalle']]) {
    test(`${ComponentName} ${status !== 503 ? 'retira datos privados y revalida permisos' : 'conserva datos recuperables'} ante HTTP ${status}`, async (t) => {
      let failure = false;
      globalThis.fetch = async (path) => failure ? response({ mensaje: 'Consulta rechazada' }, status)
        : response(path === '/api/delivery/viajes' ? [{ id: 1 }] : path === '/api/delivery/viajes/1' ? trip : path === '/api/pedidos/481' ? order : [order]);
      const Component = { Orders, DeliveryPanel, OrderDetail }[ComponentName];
      const container = await mount(t, Component, { id: 481, onClose() {} });
      if (ComponentName === 'Orders') await settleSearch();
      assert.match(container.textContent, /Cliente privado/);
      assert.match(container.textContent, /Domicilio privado/);
      const refreshes = auth.refreshes;
      failure = true;
      await act(async () => reactProps(button(container, label)).onClick());
      if (ComponentName === 'Orders') await settleSearch();
      if (status !== 503) {
        assert.doesNotMatch(container.textContent, /Cliente privado|Domicilio privado/);
        assert.ok(auth.refreshes > refreshes);
      } else {
        assert.match(container.textContent, /Cliente privado/);
        assert.match(container.textContent, /Domicilio privado/);
        assert.equal(auth.refreshes, refreshes);
      }
    });
  }
}
