import assert from 'node:assert/strict';
import { after, before, beforeEach, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import 'sonner';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let dom, server, createRoot, Menu, CartDrawer, ChatDrawer, store, chat, whatsapp;
const originalFetch = globalThis.fetch;
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
const storage = new Map();
const product = { id: 1, name: 'Burger', description: '', category: 'Nuestras Burgers', active: true, available: true, price: 100, variants: [{ name: 'Simple', price: 100 }, { name: 'Doble', price: 200 }], removableIngredients: ['Queso'] };
const response = (value, status = 200) => ({ ok: status < 400, status, json: async () => value });
before(async () => {
  dom = installMinimalDom();
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) } });
  ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'ordering-context', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return `export const state={catalog:[],catalogStatus:'ready',cart:[]}; export const actions=[]; export const loads=[]; const refreshCatalog=(signal,force)=>{loads.push({signal,force});return Promise.resolve()}; export const useData=()=>({state,dispatch:(action)=>actions.push(action),refreshCatalog});`;
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Menu } = await server.ssrLoadModule('/src/ordering/Menu.jsx'));
  ({ default: CartDrawer } = await server.ssrLoadModule('/src/ordering/CartDrawer.jsx'));
  ({ default: ChatDrawer } = await server.ssrLoadModule('/src/ordering/ChatDrawer.jsx'));
  store = await server.ssrLoadModule('/src/shared/store/DataContext.jsx');
  chat = await server.ssrLoadModule('/src/ordering/chatDemo.js');
  whatsapp = await server.ssrLoadModule('/src/ordering/whatsapp.js');
});
beforeEach(() => { storage.clear(); store.state.catalog = [product]; store.state.cart = [{ id: 1, name: 'Burger', price: 100, quantity: 1 }]; store.actions.length = 0; store.loads.length = 0; });
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); if (originalStorage) Object.defineProperty(globalThis, 'sessionStorage', originalStorage); else delete globalThis.sessionStorage; });
async function mount(t, Component, props = {}, router = false) {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const render = (next = props) => act(async () => root.render(router ? createElement(MemoryRouter, null, createElement(Component, next)) : createElement(Component, next)));
  await render();
  container.rerender = render;
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
const byId = (container, id) => elements(container, (node) => node.getAttribute?.('id') === id)[0];
const button = (container, label) => elements(container, (node) => node.localName === 'button' && (node.textContent.includes(label) || node.getAttribute('aria-label')?.includes(label)))[0];
const change = (node, value) => act(async () => reactProps(node).onChange({ target: { value } }));

test('menú solicita su catálogo aunque la sesión inicial ya sea de personal', async (t) => {
  store.state.catalogStatus = 'loading';
  await mount(t, Menu, {}, true);
  assert.equal(store.loads.length, 1);
  store.state.catalogStatus = 'ready';
});

test('el reintento del menú consulta catálogo directamente para cualquier rol', async (t) => {
  store.state.catalogStatus = 'error'; store.state.catalogError = 'Error de prueba';
  const container = await mount(t, Menu, {}, true);
  await act(async () => reactProps(button(container, 'Reintentar')).onClick());
  assert.equal(store.loads.at(-1).force, true);
  store.state.catalogStatus = 'ready';
});

test('reordenar variantes no cambia silenciosamente la seleccionada al agregar', async (t) => {
  const container = await mount(t, Menu, {}, true);
  const select = elements(container, (node) => node.localName === 'select')[0];
  // Elegir la segunda variante usando el valor publicado por la UI.
  await change(select, reactProps(select.options[1]).value);
  store.state.catalog = [{ ...product, variants: [...product.variants].reverse() }];
  await container.rerender();
  await act(async () => reactProps(button(container, 'Agregar Burger')).onClick());
  assert.equal(store.actions[0]?.payload.variant, 'Doble');
});

test('una personalización retirada del catálogo exige revisión antes de agregar', async (t) => {
  const container = await mount(t, Menu, {}, true);
  const checkbox = elements(container, (node) => node.localName === 'input' && reactProps(node).type === 'checkbox')[0];
  await act(async () => reactProps(checkbox).onChange({ target: { checked: true } }));
  store.state.catalog = [{ ...product, removableIngredients: [] }];
  await container.rerender();
  assert.equal(reactProps(button(container, 'Agregar Burger')).disabled, true);
  assert.match(container.textContent, /cambiaron|cambió|Revisá/);
});

test('carrito no envía cantidades fuera del contrato aunque provengan del estado', async (t) => {
  let requests = 0;
  store.state.cart[0].quantity = 51;
  globalThis.fetch = async () => { requests += 1; return response({ mensajes: [], borradores: [] }); };
  const container = await mount(t, CartDrawer, { isOpen: true, onClose() {}, chatConfig: { status: 'ready', habilitado: true } });
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.equal(requests, 0);
  assert.match(container.textContent, /50/);
});

test('un borrador con respuesta perdida permanece recuperable y bloquea contenido distinto', async () => {
  let requests = 0;
  globalThis.fetch = async () => { requests += 1; throw new TypeError('offline'); };
  const draft = { items: [{ producto_id: 1, cantidad: 1 }] };
  await assert.rejects(chat.sendChatDraft(draft));
  assert.deepEqual(chat.getPendingChatSend()?.draft, draft);
  await assert.rejects(chat.sendChatDraft({ items: [{ producto_id: 1, cantidad: 2 }] }), /envío anterior/);
  assert.equal(requests, 1);
});

test('el chat recupera un borrador incierto desde almacenamiento y reintenta su UUID', async (t) => {
  let sent;
  const draft = { items: [{ producto_id: 1, cantidad: 1 }] };
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  await assert.rejects(chat.sendChatDraft(draft));
  const pending = chat.getPendingChatSend();
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/borradores')) { sent = JSON.parse(options.body); return response({ id: 'saved', estado: 'PENDIENTE' }, 202); }
    return response(url.endsWith('/conversacion') ? { mensajes: [], borradores: [] } : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const retry = button(container, 'Reintentar mismo envío');
  assert.ok(retry, 'El borrador debe poder recuperarse desde el chat');
  await act(async () => reactProps(retry).onClick());
  assert.deepEqual(sent?.borrador, draft);
  assert.equal(sent?.solicitud_id, pending.id);
  assert.deepEqual(store.actions, [{ type: 'CLEAR_CART' }], 'El carrito recuperado no debe volver a enviarse como otro pedido');
});

test('recuperar un borrador anterior conserva productos nuevos del carrito actual', async (t) => {
  const draft = { items: [{ producto_id: 1, cantidad: 1, variante: null, aclaraciones: null }] };
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  await assert.rejects(chat.sendChatDraft(draft));
  store.state.cart = [{ id: 2, name: 'Otra burger', price: 200, quantity: 1 }];
  globalThis.fetch = async (url) => response(url.endsWith('/borradores') ? { id: 'saved-other', estado: 'PENDIENTE' } : url.endsWith('/conversacion') ? { mensajes: [], borradores: [] } : {});
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  await act(async () => reactProps(button(container, 'Reintentar mismo envío')).onClick());
  assert.deepEqual(store.actions, []);
});

test('un borrador público sin referencia ni mensaje no habilita un envío ficticio', async () => {
  globalThis.fetch = async () => response({});
  await assert.rejects(whatsapp.createWhatsAppDraft({ items: [{ producto_id: 1, cantidad: 1 }] }), /confirmar|preparar/);
});

test('el formulario público usa los mismos límites de dirección que la API', async (t) => {
  const container = await mount(t, CartDrawer, { isOpen: true, onClose() {}, chatConfig: { status: 'ready', habilitado: false } });
  await change(byId(container, 'checkout-delivery'), 'DELIVERY');
  assert.equal(reactProps(byId(container, 'checkout-street')).maxLength, 160);
  assert.equal(reactProps(byId(container, 'checkout-number')).maxLength, 30);
});

test('el envío que termina tarde conserva el carrito editado mientras esperaba', async (t) => {
  const pending = deferred();
  const started = deferred();
  globalThis.fetch = async (url) => {
    if (url.endsWith('/borradores')) { started.resolve(); return pending.promise; }
    return response(url.endsWith('/conversacion') ? { mensajes: [], borradores: [] } : {});
  };
  const props = { isOpen: true, onClose() {}, chatConfig: { status: 'ready', habilitado: true } };
  const container = await mount(t, CartDrawer, props);
  await act(async () => { reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); await started.promise; });
  store.state.cart = [{ id: 2, name: 'Burger nueva', price: 200, quantity: 1 }];
  await container.rerender({ ...props, isOpen: false });
  await act(async () => pending.resolve(response({ id: 'saved-late', estado: 'PENDIENTE' })));
  assert.deepEqual(store.actions, [], 'La respuesta anterior no debe borrar productos nuevos');
});
