import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement, useLayoutEffect, useState } from 'react';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let dom;
let createRoot;
let DataProvider;
let useData;
let OrderDetail;
let setUser;
let Feedback;
const originalFetch = globalThis.fetch;
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const order = { id: 17, numero: 88, version: 3, estado: 'PENDIENTE', tipo_entrega: 'RETIRO', cliente: 'Cliente', metodo_pago_acordado: 'EFECTIVO', total: '12000', saldo_pendiente: '12000', neto_cobrado: '0', items: [], pagos: [], historial: [] };

before(async () => {
  dom = installMinimalDom();
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, plugins: [{ name: 'auth-background', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return "let user={id:1,role:'admin',backendRole:'EMPLEADO'}; export const setUser=(value)=>{user=value}; export const useAuth=()=>({user});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ DataProvider, useData } = await server.ssrLoadModule('/src/shared/store/DataContext.jsx'));
  ({ default: OrderDetail } = await server.ssrLoadModule('/src/fulfillment/OrderDetail.jsx'));
  ({ setUser } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ default: Feedback } = await server.ssrLoadModule('/src/fulfillment/OrderOperationFeedback.jsx'));
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });

async function mount(t, child) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const render = () => root.render(createElement(DataProvider, null, child));
  await act(async () => render());
  container.rerender = render;
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
const button = (container, label) => elements(container, (node) => node.localName === 'button' && node.textContent === label)[0];

test('enviar a cocina cierra y desmonta el detalle antes de responder el servidor', async (t) => {
  const writing = deferred();
  let data;
  let writes = 0;
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'PATCH') { writes += 1; return writing.promise; }
    return response(path === '/api/pedidos/17' ? order : [order]);
  };
  function Screen() {
    const current = useData();
    useLayoutEffect(() => { data = current; });
    const [open, setOpen] = useState(true);
    return open ? createElement(OrderDetail, { id: 17, onClose: () => setOpen(false) }) : createElement('p', null, 'Tablero disponible');
  }
  const container = await mount(t, createElement(Screen));
  await act(async () => reactProps(button(container, 'Enviar a cocina')).onClick());
  assert.equal(elements(container, (node) => node.localName === 'dialog').length, 0);
  assert.match(container.textContent, /Tablero disponible/);
  assert.equal(writes, 1);
  assert.equal(data.orderOperationPending(17), true);
  assert.equal(data.startOrderOperation({ id: 17, operation: () => { writes += 1; } }), false);
  await act(async () => { writing.resolve(response({ ...order, estado: 'EN_PREPARACION', version: 4 })); });
  assert.equal(data.orderOperationPending(17), false);
  assert.equal(data.state.orders[0].estado, 'EN_PREPARACION');
  assert.equal(writes, 1);
});

test('un fallo después de cerrar conserva el pedido y un error recuperable', async (t) => {
  const writing = deferred();
  let data;
  globalThis.fetch = async () => response([order]);
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  await mount(t, createElement(Capture));
  assert.equal(typeof data.startOrderOperation, 'function');
  await act(async () => data.startOrderOperation({ id: 17, number: 88, operation: () => writing.promise }));
  await act(async () => { writing.reject(new Error('Stock insuficiente')); });
  assert.equal(data.orderOperationPending(17), false);
  assert.equal(data.state.orders[0].estado, 'PENDIENTE');
  assert.equal(data.orderOperations[0].status, 'error');
  assert.match(data.orderOperations[0].message, /Stock insuficiente/);
});

test('las operaciones de otra sesión no publican resultados ni mensajes sobre la nueva', async (t) => {
  const writing = deferred();
  let data;
  globalThis.fetch = async () => response([]);
  function Capture() { const current = useData(); useLayoutEffect(() => { data = current; }); return null; }
  const container = await mount(t, createElement(Capture));
  assert.equal(typeof data.startOrderOperation, 'function');
  await act(async () => data.startOrderOperation({ id: 17, number: 88, operation: () => writing.promise }));
  setUser({ id: 2, role: 'admin', backendRole: 'EMPLEADO' });
  t.after(() => setUser({ id: 1, role: 'admin', backendRole: 'EMPLEADO' }));
  await act(async () => container.rerender());
  assert.equal(data.orderOperations.length, 0);
  assert.equal(data.state.ordersStatus, 'ready');
  await act(async () => { writing.resolve({ ...order, estado: 'EN_PREPARACION', version: 4 }); });
  assert.equal(data.orderOperations.length, 0);
  assert.equal(data.state.orders.length, 0);
});

test('un error se puede revisar sin reenviar automáticamente la operación', async (t) => {
  const fresh = deferred();
  let data;
  let attempts = 0;
  globalThis.fetch = async (path) => path === '/api/pedidos/17' ? fresh.promise : response([order]);
  function Screen() { const current = useData(); useLayoutEffect(() => { data = current; }); return createElement(Feedback); }
  const container = await mount(t, createElement(Screen));
  await act(async () => data.startOrderOperation({ id: 17, number: 88, operation: async () => { attempts += 1; throw new Error('No disponible'); } }));
  assert.match(container.textContent, /No disponible/);
  await act(async () => reactProps(button(container, 'Revisar pedido')).onClick());
  for (let i = 0; i < 25 && !button(container, 'Enviar a cocina'); i += 1) await act(async () => { await new Promise((resolve) => setImmediate(resolve)); });
  assert.ok(button(container, 'Enviar a cocina'));
  assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, true);
  await act(async () => { fresh.resolve(response(order)); });
  assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, false);
  assert.equal(attempts, 1);
});

test('cobrar cierra inmediatamente y conserva el UUID para recuperar una respuesta perdida', async (t) => {
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  const storage = new Map();
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) } });
  t.after(() => { if (originalStorage) Object.defineProperty(globalThis, 'sessionStorage', originalStorage); else delete globalThis.sessionStorage; });
  const writing = deferred();
  let data;
  const bodies = [];
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'POST') { bodies.push(options.body); return bodies.length === 1 ? writing.promise : response({ pago: { id: 55 }, pedido: { ...order, neto_cobrado: '12000', saldo_pendiente: '0' } }); }
    return response(path === '/api/pedidos/17' ? order : [order]);
  };
  let reopen;
  function Screen() {
    const current = useData(); useLayoutEffect(() => { data = current; });
    const [open, setOpen] = useState(true);
    useLayoutEffect(() => { reopen = () => setOpen(true); });
    return open ? createElement(OrderDetail, { id: 17, onClose: () => setOpen(false) }) : createElement('p', null, 'Tablero');
  }
  const container = await mount(t, createElement(Screen));
  const submit = async () => { await act(async () => { void reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); }); };
  await submit();
  assert.equal(elements(container, (node) => node.localName === 'dialog').length, 0);
  assert.equal(data.orderOperationPending(17), true);
  assert.ok(storage.get('monu-payment:1:17'));
  await act(async () => { writing.reject(new Error('Respuesta perdida')); });
  assert.equal(data.orderOperations[0].status, 'error');
  await act(async () => reopen());
  assert.ok(button(container, 'Reintentar operación guardada'));
  await submit();
  assert.deepEqual(bodies[1], bodies[0]);
  assert.equal(storage.has('monu-payment:1:17'), false);
  assert.equal(Number(data.state.orders[0].saldo_pendiente), 0);
});

test('una transferencia de la sesión anterior no inicia otra llamada con la sesión nueva', async (t) => {
  const writing = deferred();
  let calls = 0;
  const transfer = { ...order, metodo_pago_acordado: 'TRANSFERENCIA' };
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'POST') { calls += 1; return calls === 1 ? writing.promise : response({ id: 55, estado: 'CONCILIADO' }); }
    return response(path === '/api/pedidos/17' ? transfer : []);
  };
  function Screen() { const [open, setOpen] = useState(true); return open ? createElement(OrderDetail, { id: 17, onClose: () => setOpen(false) }) : null; }
  const container = await mount(t, createElement(Screen));
  await act(async () => { void reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); });
  setUser({ id: 3, role: 'admin', backendRole: 'EMPLEADO' });
  t.after(() => setUser({ id: 1, role: 'admin', backendRole: 'EMPLEADO' }));
  await act(async () => container.rerender());
  await act(async () => { writing.resolve(response({ id: 55, estado: 'PENDIENTE' })); });
  assert.equal(calls, 1);
});

for (const existing of [false, true]) {
  test(`confirmar transferencia ${existing ? 'pendiente' : 'nueva'} conserva el detalle y habilita cocina al confirmarse`, async (t) => {
    const writing = deferred();
    const transfer = { ...order, metodo_pago_acordado: 'TRANSFERENCIA', pagos: existing ? [{ id: 55, tipo: 'COBRO', estado: 'PENDIENTE', metodo_pago: 'TRANSFERENCIA', monto: '12000' }] : [] };
    const paid = { ...transfer, version: 4, saldo_pendiente: '0', neto_cobrado: '12000', pagos: [{ id: 55, tipo: 'COBRO', estado: 'CONCILIADO', metodo_pago: 'TRANSFERENCIA', monto: '12000' }] };
    let posts = 0;
    let reads = 0;
    let closed = 0;
    const recordClose = () => { closed += 1; };
    globalThis.fetch = async (path, options = {}) => {
      if (options.method === 'POST') { posts += 1; return writing.promise; }
      if (options.method === 'PATCH') return response({ ...paid, estado: 'EN_PREPARACION', version: 5 });
      if (path === '/api/pedidos/17') { reads += 1; return response(transfer); }
      return response([transfer]);
    };
    function Screen() { const [open, setOpen] = useState(true); return open ? createElement(OrderDetail, { id: 17, onClose: () => { recordClose(); setOpen(false); } }) : null; }
    const container = await mount(t, createElement(Screen));
    const readsBefore = reads;
    const confirm = elements(container, (node) => node.localName === 'button' && node.textContent.startsWith('Confirmar ingreso de'))[0];
    assert.ok(confirm);
    await act(async () => {
      if (existing) reactProps(confirm).onClick();
      else void reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} });
    });
    assert.equal(closed, 0);
    assert.equal(elements(container, (node) => node.localName === 'dialog').length, 1);
    assert.equal(reactProps(confirm).disabled, true);
    await act(async () => { writing.resolve(response({ id: 55, estado: 'CONCILIADO', pedido: paid })); });
    assert.match(container.textContent, /Pagado/);
    assert.equal(closed, 0);
    assert.equal(reads, readsBefore, 'La respuesta confirmada actualiza el detalle sin otro GET');
    assert.equal(posts, 1);
    assert.equal(reactProps(button(container, 'Enviar a cocina')).disabled, false);
    await act(async () => reactProps(button(container, 'Enviar a cocina')).onClick());
    assert.equal(closed, 1);
  });
}

test('un fallo de transferencia deja el detalle abierto y conserva el intento para reintentar', async (t) => {
  const transfer = { ...order, metodo_pago_acordado: 'TRANSFERENCIA' };
  const bodies = [];
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === 'POST') {
      bodies.push(options.body);
      if (bodies.length === 1) throw Error('Respuesta perdida');
      return response({ id: 55, estado: 'CONCILIADO', pedido: { ...transfer, version: 4, neto_cobrado: '12000', saldo_pendiente: '0' } });
    }
    return response(path === '/api/pedidos/17' ? transfer : [transfer]);
  };
  let closed = 0;
  const container = await mount(t, createElement(OrderDetail, { id: 17, onClose: () => { closed += 1; } }));
  const submit = async () => { await act(async () => { void reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); }); };
  await submit();
  assert.equal(closed, 0);
  assert.match(container.textContent, /Respuesta perdida/);
  assert.equal(reactProps(button(container, 'Reintentar operación guardada')).disabled, true);
  await act(async () => { await reactProps(button(container, 'Actualizar detalle')).onClick(); });
  assert.equal(reactProps(button(container, 'Reintentar operación guardada')).disabled, false);
  await submit();
  assert.equal(closed, 0);
  assert.equal(bodies[1], bodies[0]);
  assert.match(container.textContent, /Pagado/);
});

test('una respuesta antigua no borra el UUID al volver a entrar con la misma cuenta', async (t) => {
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  const storage = new Map();
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) } });
  t.after(() => { if (originalStorage) Object.defineProperty(globalThis, 'sessionStorage', originalStorage); else delete globalThis.sessionStorage; });
  const writing = deferred();
  globalThis.fetch = async (path, options = {}) => options.method === 'POST' ? writing.promise : response(path === '/api/pedidos/17' ? order : []);
  function Screen() { const [open, setOpen] = useState(true); return open ? createElement(OrderDetail, { id: 17, onClose: () => setOpen(false) }) : null; }
  const container = await mount(t, createElement(Screen));
  await act(async () => { void reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); });
  const attempt = storage.get('monu-payment:1:17');
  assert.ok(attempt);
  setUser({ id: 1, role: 'admin', backendRole: 'EMPLEADO' });
  await act(async () => container.rerender());
  await act(async () => { writing.resolve(response({ pago: { id: 55 }, pedido: { ...order, neto_cobrado: '12000', saldo_pendiente: '0' } })); });
  assert.equal(storage.get('monu-payment:1:17'), attempt);
});
