import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { act, createElement } from 'react';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';

let server;
let chat;
let dom;
let createRoot;
let ChatDrawer;
let CartDrawer;
let testStore;
let tick;
const originalFetch = globalThis.fetch;
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

before(async () => {
  dom = installMinimalDom();
  window.setInterval = (callback) => { tick = callback; return 1; };
  window.clearInterval = () => { tick = null; };
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ configFile: false, cacheDir: `node_modules/.vite-chat-test-${process.pid}`, plugins: [{ name: 'datos-chat-test', enforce: 'pre', load(id) {
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return "export const state={cart:[{id:1,quantity:1,price:100,name:'Hamburguesa'}]}; export const actions=[]; export const useData=()=>({state,dispatch:(action)=>actions.push(action)});";
    return null;
  } }, react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  chat = await server.ssrLoadModule('/src/ordering/chatDemo.js');
  ({ default: ChatDrawer } = await server.ssrLoadModule('/src/ordering/ChatDrawer.jsx'));
  ({ default: CartDrawer } = await server.ssrLoadModule('/src/ordering/CartDrawer.jsx'));
  testStore = await server.ssrLoadModule('/src/shared/store/DataContext.jsx');
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); });

async function mount(t, Component, props) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(Component, props)));
  container.rerender = async (next) => act(async () => root.render(createElement(Component, next)));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); document.hidden = false; });
  return container;
}

const button = (container, text) => elements(container, (node) => node.localName === 'button' && node.textContent.includes(text))[0];
const conversation = () => ({ interpretador: 'simulado', gemini_configurado: false, mensajes: [{ id: 'm1', direccion: 'bot', texto: 'Confirmá tu pedido', estado: 'SIMULADO', creado_en: '2026-10-20T15:00:00Z', tiene_archivo: false }], borradores: [] });

test('recupera sesión por cookie y usa protección CSRF en mutaciones', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({ url, options }); return response({ mensajes: [], borradores: [] }); };
  await chat.openChatSession();
  assert.deepEqual(calls.map(({ url }) => url), ['/api/chat-demo/sesion', '/api/chat-demo/conversacion']);
  assert.equal(calls[0].options.headers['X-Chat-Demo'], '1');
  assert.ok(calls.every(({ options }) => options.credentials === 'include'));
});

test('aperturas concurrentes comparten inicialización y recuperan sus conversaciones', async () => {
  const pending = deferred();
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(url); return url.endsWith('/sesion') ? pending.promise : response(conversation()); };
  const first = chat.openChatSession();
  const second = chat.openChatSession();
  assert.equal(calls.filter((url) => url.endsWith('/sesion')).length, 1);
  pending.resolve(response({}));
  await Promise.all([first, second]);
  assert.equal(calls.filter((url) => url.endsWith('/conversacion')).length, 2);
});

test('inicialización fallida libera el intento compartido para volver a abrir', async () => {
  let posts = 0;
  globalThis.fetch = async (url) => {
    if (url.endsWith('/sesion')) { posts += 1; return posts === 1 ? response({ detail: 'Servicio no disponible' }, 503) : response({}); }
    return response(conversation());
  };
  const results = await Promise.allSettled([chat.openChatSession(), chat.openChatSession()]);
  assert.ok(results.every((result) => result.status === 'rejected'));
  assert.equal(posts, 1);
  await chat.openChatSession();
  assert.equal(posts, 2);
});

test('reintento conserva UUID y contenido sin volver a crear un borrador público', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (calls.length === 1) throw new Error('Respuesta perdida');
    return response({ id: 'entrada', estado: 'PENDIENTE' }, 202);
  };
  const draft = { items: [{ producto_id: 1, cantidad: 2 }], tipo_entrega: null, metodo_pago: null };
  await assert.rejects(chat.sendChatDraft(draft), /Respuesta perdida/);
  await chat.sendChatDraft(draft);
  assert.deepEqual(calls.map(({ url }) => url), ['/api/chat-demo/borradores', '/api/chat-demo/borradores']);
  assert.equal(calls[0].options.body, calls[1].options.body);
  assert.deepEqual(JSON.parse(calls[1].options.body).borrador, draft);
});

test('comprobante se envía binario con tipo y UUID, y rechaza tamaño o tipo inválido', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({ url, options }); return response({ id: 'archivo', estado: 'PENDIENTE' }, 202); };
  await assert.rejects(chat.sendChatReceipt(new Blob(['x'], { type: 'text/html' })), /PDF, PNG o JPEG/);
  await assert.rejects(chat.sendChatReceipt(new Blob([new Uint8Array(2 * 1024 * 1024 + 1)], { type: 'application/pdf' })), /2 MiB/);
  const file = new Blob(['%PDF-1.7'], { type: 'application/pdf' });
  await chat.sendChatReceipt(file);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.body, file);
  assert.equal(calls[0].options.headers['Content-Type'], 'application/pdf');
  assert.match(calls[0].options.headers['X-Solicitud-Id'], /^[a-f0-9-]{36}$/);
});

test('texto vacío o excesivo no hace llamadas y un fallo no simula éxito', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return response({ detail: 'Sesión vencida' }, 401); };
  await assert.rejects(chat.sendChatText(' '), /1 a 2000/);
  await assert.rejects(chat.sendChatText('x'.repeat(2001)), /1 a 2000/);
  assert.equal(calls, 0);
  await assert.rejects(chat.sendChatText('Consultar mi pedido'), /Sesión vencida/);
});

test('chat recupera historial al reabrir, suspende polling oculto y no inventa respuestas', async (t) => {
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(url); return response(url.endsWith('/conversacion') ? conversation() : {}); };
  const props = { isOpen: true, onClose() {} };
  const container = await mount(t, ChatDrawer, props);
  assert.match(container.textContent, /Confirmá tu pedido/);
  assert.match(container.textContent, /Disponible en la demo/);
  assert.match(container.textContent, /Interpretación simulada/);
  const log = elements(container, (node) => node.getAttribute?.('role') === 'log')[0];
  assert.equal(log.getAttribute('aria-live'), 'polite');
  assert.equal(log.getAttribute('aria-relevant'), 'additions');
  assert.equal(document.activeElement.getAttribute('id'), 'chat-text');
  const count = calls.length;
  document.hidden = true;
  await act(async () => tick());
  assert.equal(calls.length, count);
  document.hidden = false;
  await container.rerender({ ...props, isOpen: false });
  assert.equal(tick, null);
  await container.rerender(props);
  assert.equal(calls.filter((url) => url.endsWith('/conversacion')).length, 2);
  assert.equal(elements(container, (node) => node.localName === 'li').length, 1);
});

test('error de envío conserva texto y reintento aunque el polling siga funcionando', async (t) => {
  const sent = [];
  let fail = true;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/mensajes')) { sent.push(options.body); if (fail) throw new Error('Respuesta perdida'); return response({ estado: 'PENDIENTE' }, 202); }
    return response(url.endsWith('/conversacion') ? conversation() : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: 'Sin tomate' } }));
  await act(async () => reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }));
  assert.match(container.textContent, /Respuesta perdida/);
  await act(async () => tick());
  assert.ok(button(container, 'Reintentar mismo envío'));
  assert.equal(reactProps(input).value, 'Sin tomate');
  assert.doesNotMatch(elements(container, (node) => node.localName === 'ol')[0].textContent, /Sin tomate/);
  fail = false;
  await act(async () => reactProps(button(container, 'Reintentar mismo envío')).onClick());
  assert.equal(sent.length, 2);
  assert.equal(sent[0], sent[1]);
  assert.equal(reactProps(input).value, '');
});

test('carrito entrega un único borrador al chat y permite completar datos allí', async (t) => {
  const pending = deferred();
  const started = deferred();
  const calls = [];
  let opened = 0;
  testStore.actions.length = 0;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith('/borradores')) { started.resolve(); return pending.promise; }
    return response(url.endsWith('/conversacion') ? conversation() : {});
  };
  const container = await mount(t, CartDrawer, { isOpen: true, onClose() {}, chatConfig: { status: 'ready', habilitado: true }, onOpenChat() { opened += 1; } });
  assert.match(container.textContent, /El pedido se registra al procesar el carrito con los datos completos/);
  assert.ok(elements(container, (node) => node.localName === 'section' && node.getAttribute('aria-label') === 'Entrega y pago del pedido').length);
  assert.equal(elements(container, (node) => node.getAttribute?.('aria-labelledby') === 'checkout-contact').length, 0);
  assert.equal(elements(container, (node) => node.getAttribute?.('name') === 'telefono').length, 0);
  for (const id of ['checkout-delivery', 'checkout-payment']) await act(async () => reactProps(elements(container, (node) => node.getAttribute?.('id') === id)[0]).onChange({ target: { value: '' } }));
  const submit = reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit;
  await act(async () => { submit({ preventDefault() {} }); submit({ preventDefault() {} }); await started.promise; });
  assert.equal(calls.filter(({ url }) => url.endsWith('/borradores')).length, 1);
  assert.equal(opened, 0);
  const draft = JSON.parse(calls.find(({ url }) => url.endsWith('/borradores')).options.body).borrador;
  assert.equal(draft.tipo_entrega, null);
  assert.equal(draft.metodo_pago, null);
  assert.equal(draft.contacto, null);
  assert.equal(draft.items.length, 1);
  await act(async () => pending.resolve(response({ id: 'entrada', estado: 'PENDIENTE' }, 202)));
  assert.equal(opened, 1);
  assert.deepEqual(testStore.actions, [{ type: 'CLEAR_CART' }]);
  assert.ok(calls.every(({ url }) => !url.startsWith('/api/whatsapp')));
});

test('un error de configuración queda visible en carrito y permite consultar de nuevo', async (t) => {
  let retried = 0;
  const container = await mount(t, CartDrawer, { isOpen: true, onClose() {}, chatConfig: { status: 'error', error: 'No se pudo consultar la demo' }, onRetryChatConfig() { retried += 1; } });
  assert.match(container.textContent, /No se pudo consultar la demo/);
  assert.equal(reactProps(elements(container, (node) => node.localName === 'button' && reactProps(node).type === 'submit')[0]).disabled, true);
  await act(async () => reactProps(button(container, 'Reintentar disponibilidad del chat')).onClick());
  assert.equal(retried, 1);
});

test('sin Gemini ofrece atención humana por el mismo chat y conserva el texto sin enviar', async (t) => {
  const sent = deferred();
  let request;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/mensajes')) { request = JSON.parse(options.body); sent.resolve(); return response({ estado: 'PENDIENTE' }, 202); }
    return response(url.endsWith('/conversacion') ? { ...conversation(), interpretador: 'real', gemini_configurado: false } : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: 'Mi consulta pendiente' } }));
  await act(async () => { reactProps(button(container, 'Pedir atención humana')).onClick(); await sent.promise; });
  assert.equal(request.texto, 'quiero hablar con una persona');
  assert.equal(reactProps(input).value, 'Mi consulta pendiente');
});

test('borrador vencido muestra vencimiento real y un pedido creado conserva su estado', async (t) => {
  const expired = '2020-01-02T15:00:00Z';
  globalThis.fetch = async (url) => response(url.endsWith('/conversacion') ? { ...conversation(), borradores: [
    { pedido_id: null, estado: 'PENDIENTE', expira_en: expired },
    { pedido_id: 12, numero: 5, estado_pedido: 'CONFIRMADO', expira_en: expired, total: 100 },
  ] } : {});
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  assert.match(container.textContent, /Borrador vencido/);
  assert.doesNotMatch(container.textContent, /pendiente de completar o confirmar/);
  assert.match(container.textContent, /Pedido #5 · CONFIRMADO/);
  const expiration = elements(container, (node) => node.localName === 'time' && reactProps(node).dateTime === expired)[0];
  assert.ok(expiration);
  assert.equal(expiration.textContent, new Date(expired).toLocaleString('es-AR'));
});
