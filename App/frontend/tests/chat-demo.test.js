import assert from 'node:assert/strict';
import { before, beforeEach, after, test } from 'node:test';
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
let scheduledDelay;
const originalFetch = globalThis.fetch;
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
const storage = new Map();
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

before(async () => {
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) } });
  dom = installMinimalDom();
  window.setTimeout = (callback, delay) => { tick = callback; scheduledDelay = delay; return 1; };
  window.clearTimeout = () => { tick = null; };
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
beforeEach(() => storage.clear());
after(async () => { globalThis.fetch = originalFetch; await server?.close(); dom?.restore(); if (originalStorage) Object.defineProperty(globalThis, 'sessionStorage', originalStorage); else delete globalThis.sessionStorage; });

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
const control = (container, label) => elements(container, (node) => node.localName === 'button' && node.getAttribute('aria-label') === label)[0];
const openInfo = (container) => act(async () => reactProps(control(container, 'Información y opciones del chat')).onClick());
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

test('respuesta inválida conserva UUID y no confirma un envío que no está persistido', async () => {
  const requests = [];
  globalThis.fetch = async (_url, options) => { requests.push(JSON.parse(options.body)); return response(requests.length === 1 ? null : { id: 'entrada', estado: 'PENDIENTE' }, 202); };
  await assert.rejects(chat.sendChatText('Sin cebolla'), /confirmar/);
  await chat.sendChatText('Sin cebolla');
  assert.equal(requests[0].solicitud_id, requests[1].solicitud_id);
});

test('recarga recupera el mismo envío incierto y lo reconcilia sólo con su ID del servidor', async () => {
  let request;
  globalThis.fetch = async (_url, options) => { request = JSON.parse(options.body); throw new Error('Respuesta perdida'); };
  await assert.rejects(chat.sendChatText('Agregar una Crispy'), /Respuesta perdida/);
  const reloaded = await server.ssrLoadModule('/src/ordering/chatDemo.js?recarga');
  assert.equal(reloaded.getPendingChatSend().text, 'Agregar una Crispy');
  assert.equal(reloaded.reconcileChatSend({ mensajes: [{ id: 'otra-entrada', texto: 'Agregar una Crispy' }] }), false);
  let repeated;
  globalThis.fetch = async (_url, options) => { repeated = JSON.parse(options.body); return response({ id: `web:sesion:${request.solicitud_id}`, estado: 'PROCESADO' }); };
  await reloaded.sendChatText('Agregar una Crispy');
  assert.equal(repeated.solicitud_id, request.solicitud_id);
  assert.equal(reloaded.getPendingChatSend(), null);
});

test('un envío incierto impide reemplazar la solicitud por otro mensaje', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error('Sin conexión'); };
  await assert.rejects(chat.sendChatText('Mensaje original'), /Sin conexión/);
  await assert.rejects(chat.sendChatText('Otro mensaje'), /envío anterior/);
  assert.equal(calls, 1);
});

test('timeout acota una conexión colgada, aborta la solicitud y conserva el mismo UUID', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const started = deferred();
  let options;
  globalThis.fetch = async (_url, requestOptions) => { options = requestOptions; started.resolve(); return new Promise(() => {}); };
  const sending = chat.sendChatText('Pedido con respuesta demorada');
  const rejected = assert.rejects(sending, /tiempo/);
  await started.promise;
  t.mock.timers.tick(15000);
  await rejected;
  assert.equal(options.signal.aborted, true);
  assert.equal(chat.getPendingChatSend().id, JSON.parse(options.body).solicitud_id);
});

test('rechazo HTTP permite corregir el texto y conserva el UUID para replay del original', async () => {
  const requests = [];
  globalThis.fetch = async (_url, options) => { requests.push(JSON.parse(options.body)); return requests.length === 1 ? response({ detail: 'Contenido no permitido' }, 422) : response({ id: 'entrada', estado: 'PENDIENTE' }); };
  await assert.rejects(chat.sendChatText('Mensaje rechazado'), (failure) => failure.status === 422);
  assert.equal(chat.getPendingChatSend(), null);
  await chat.sendChatText('Mensaje corregido');
  await chat.sendChatText('Mensaje rechazado');
  assert.equal(requests[0].solicitud_id, requests[2].solicitud_id);
});

test('comprobante incierto se recupera por el mismo contenido tras recargar sin guardar el binario', async () => {
  let first;
  globalThis.fetch = async (_url, options) => { first = options; throw new Error('Respuesta perdida'); };
  const file = new Blob(['%PDF-original'], { type: 'application/pdf' });
  await assert.rejects(chat.sendChatReceipt(file), /Respuesta perdida/);
  const reloaded = await server.ssrLoadModule('/src/ordering/chatDemo.js?recarga-comprobante');
  assert.equal(reloaded.getPendingChatSend().fileName, 'comprobante');
  assert.equal(reloaded.getPendingChatSend().file, undefined);
  await assert.rejects(reloaded.sendChatReceipt(new Blob(['%PDF-otro'], { type: 'application/pdf' })), /envío anterior/);
  let repeated;
  globalThis.fetch = async (_url, options) => { repeated = options; return response({ id: 'archivo', estado: 'PENDIENTE' }); };
  await reloaded.sendChatReceipt(file);
  assert.equal(first.headers['X-Solicitud-Id'], repeated.headers['X-Solicitud-Id']);
});

test('sin espacio en sessionStorage conserva el envío incierto en memoria durante la sesión', async () => {
  const setItem = globalThis.sessionStorage.setItem;
  globalThis.sessionStorage.setItem = () => { throw new Error('Sin espacio'); };
  try {
    const privateChat = await server.ssrLoadModule('/src/ordering/chatDemo.js?sin-espacio');
    globalThis.fetch = async () => { throw new Error('Respuesta perdida'); };
    await assert.rejects(privateChat.sendChatText('Conservar este intento'), /Respuesta perdida/);
    assert.equal(privateChat.getPendingChatSend().text, 'Conservar este intento');
    await assert.rejects(privateChat.sendChatText('Otro mensaje'), /envío anterior/);
  } finally { globalThis.sessionStorage.setItem = setItem; }
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
  assert.doesNotMatch(container.textContent, /Disponible en la demo|Interpretación simulada/);
  assert.match(container.textContent, /Demo/);
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
  const firstAttempt = deferred();
  const retryAttempt = deferred();
  let fail = true;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/mensajes')) { sent.push(options.body); (sent.length === 1 ? firstAttempt : retryAttempt).resolve(); if (fail) throw new Error('Respuesta perdida'); return response({ id: 'entrada', estado: 'PENDIENTE' }, 202); }
    return response(url.endsWith('/conversacion') ? conversation() : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: 'Sin tomate' } }));
  await act(async () => { reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); await firstAttempt.promise; });
  assert.match(container.textContent, /Respuesta perdida/);
  await act(async () => tick());
  assert.ok(button(container, 'Reintentar mismo envío'));
  assert.equal(reactProps(input).value, 'Sin tomate');
  assert.doesNotMatch(elements(container, (node) => node.localName === 'ol')[0].textContent, /Sin tomate/);
  fail = false;
  await act(async () => { reactProps(button(container, 'Reintentar mismo envío')).onClick(); await retryAttempt.promise; });
  assert.equal(sent.length, 2);
  assert.equal(sent[0], sent[1]);
  assert.equal(reactProps(input).value, '');
});

test('al recargar el chat muestra el intento incierto y un historial persistido lo resuelve sin reenviar', async (t) => {
  let request;
  globalThis.fetch = async (_url, options) => { request = JSON.parse(options.body); throw new Error('Respuesta perdida'); };
  await assert.rejects(chat.sendChatText('Sin bacon en la Crispy'), /Respuesta perdida/);
  const history = deferred();
  let posts = 0;
  globalThis.fetch = async (url) => { if (url.endsWith('/conversacion')) return history.promise; posts += 1; return response({}); };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  assert.ok(button(container, 'Reintentar mismo envío'));
  assert.equal(reactProps(elements(container, (node) => node.localName === 'textarea')[0]).value, 'Sin bacon en la Crispy');
  await act(async () => history.resolve(response({ ...conversation(), mensajes: [{ id: `web:sesion:${request.solicitud_id}`, direccion: 'cliente', texto: request.texto, estado: 'PROCESADO', creado_en: '2026-10-20T15:00:00Z' }] })));
  assert.equal(button(container, 'Reintentar mismo envío'), undefined);
  assert.equal(chat.getPendingChatSend(), null);
  assert.equal(posts, 1);
});

test('historial desactualizado informa el fallo y bloquea nuevos envíos hasta recuperar conexión', async (t) => {
  let fail = false;
  globalThis.fetch = async (url) => {
    if (url.endsWith('/conversacion') && fail) return response({ detail: 'Servicio no disponible' }, 503);
    return response(url.endsWith('/conversacion') ? conversation() : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  await openInfo(container);
  fail = true;
  await act(async () => tick());
  assert.match(container.textContent, /historial visible puede estar desactualizado/);
  assert.equal(reactProps(button(container, 'Ver opciones')).disabled, true);
  assert.match(container.textContent, /Confirmá tu pedido/);
  fail = false;
  await act(async () => reactProps(button(container, 'Actualizar conversación')).onClick());
  assert.equal(reactProps(button(container, 'Ver opciones')).disabled, false);
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
    if (url.endsWith('/mensajes')) { request = JSON.parse(options.body); sent.resolve(); return response({ id: 'entrada', estado: 'PENDIENTE' }, 202); }
    return response(url.endsWith('/conversacion') ? { ...conversation(), interpretador: 'real', gemini_configurado: false } : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  await openInfo(container);
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: 'Mi consulta pendiente' } }));
  await act(async () => { reactProps(button(container, 'Pedir atención humana')).onClick(); await sent.promise; });
  assert.equal(request.texto, 'empleado');
  assert.equal(reactProps(input).value, 'Mi consulta pendiente');
});

for (const [label, text] of [['Ver opciones', 'ayuda'], ['Consultar resumen', 'resumen'], ['Pedir atención humana', 'empleado']]) {
  test(`${label} devuelve el foco al compositor y conserva su borrador`, async (t) => {
    const sent = deferred();
    let request;
    globalThis.fetch = async (url, options) => {
      if (url.endsWith('/mensajes')) { request = JSON.parse(options.body); sent.resolve(); return response({ id: 'atajo', estado: 'PENDIENTE' }, 202); }
      return response(url.endsWith('/conversacion') ? conversation() : {});
    };
    const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
    const input = elements(container, (node) => node.localName === 'textarea')[0];
    await act(async () => reactProps(input).onChange({ target: { value: 'Mi próximo mensaje' } }));
    await openInfo(container);
    const shortcut = button(container, label);
    shortcut.focus();
    await act(async () => { reactProps(shortcut).onClick(); await sent.promise; });
    assert.equal(document.activeElement.getAttribute('id'), 'chat-text');
    assert.equal(reactProps(input).value, 'Mi próximo mensaje');
    assert.equal(request.texto, text);
    assert.equal(control(container, 'Información y opciones del chat').getAttribute('aria-expanded'), 'false');
  });
}

test('borrador vencido muestra vencimiento real y un pedido creado conserva su estado', async (t) => {
  const expired = '2020-01-02T15:00:00Z';
  globalThis.fetch = async (url) => response(url.endsWith('/conversacion') ? { ...conversation(), borradores: [
    { pedido_id: null, estado: 'PENDIENTE', expira_en: expired },
    { pedido_id: 12, numero: 5, estado_pedido: 'CONFIRMADO', expira_en: expired, total: 100 },
  ] } : {});
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  assert.doesNotMatch(container.textContent, /Borrador vencido|Pedido #5/);
  await openInfo(container);
  assert.match(container.textContent, /Borrador vencido/);
  assert.doesNotMatch(container.textContent, /pendiente de completar o confirmar/);
  assert.match(container.textContent, /Pedido #5 · CONFIRMADO/);
  const expiration = elements(container, (node) => node.localName === 'time' && reactProps(node).dateTime === expired)[0];
  assert.ok(expiration);
  assert.equal(expiration.textContent, new Date(expired).toLocaleString('es-AR'));
});

test('chat compacto revela información y comprobantes sólo al pedirlos y formatea el bot sin interpretar HTML', async (t) => {
  globalThis.fetch = async (url) => response(url.endsWith('/conversacion') ? { ...conversation(), mensajes: [{ ...conversation().mensajes[0], texto: '*Tu pedido*\n<script>peligro</script>' }] } : {});
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  assert.doesNotMatch(container.textContent, /Demostración:|Mayús|2 MiB|Interpretación simulada|Disponible en la demo/);
  assert.equal(elements(container, (node) => node.localName === 'strong')[0].textContent, 'Tu pedido');
  assert.equal(elements(container, (node) => node.localName === 'script').length, 0);
  assert.match(container.textContent, /<script>peligro<\/script>/);
  assert.equal(reactProps(elements(container, (node) => node.localName === 'textarea')[0]).rows, 1);
  assert.ok(control(container, 'Enviar mensaje'));
  await openInfo(container);
  assert.match(container.textContent, /Demostración:|Interpretación simulada/);
  await act(async () => reactProps(control(container, 'Adjuntar comprobante')).onClick());
  assert.match(container.textContent, /2 MiB|no acredita dinero/);
});

test('envío aparece al instante, conserva acuse sin duplicarlo y consulta la respuesta sin reabrir sesión', async (t) => {
  const acknowledgement = deferred();
  const started = deferred();
  const persisted = { id: 'entrada-rapida', direccion: 'cliente', texto: 'Agregar una Crispy', estado: 'PENDIENTE', creado_en: '2026-10-20T15:00:00Z' };
  let calls = [];
  let history = conversation();
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url.endsWith('/mensajes')) { started.resolve(); return acknowledgement.promise; }
    return response(url.endsWith('/conversacion') ? history : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: persisted.texto } }));
  await act(async () => { reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); await started.promise; });
  const log = elements(container, (node) => node.localName === 'ol')[0];
  assert.match(log.textContent, /Agregar una Crispy.*Enviando/s);
  assert.equal(reactProps(input).value, '');
  assert.equal(reactProps(input).disabled, false);
  await act(async () => reactProps(input).onChange({ target: { value: 'Y sin cebolla' } }));
  await act(async () => acknowledgement.resolve(response({ id: persisted.id, estado: 'PENDIENTE' }, 202)));
  assert.match(log.textContent, /Agregar una Crispy/);
  assert.doesNotMatch(log.textContent, /Enviando/);
  assert.equal(calls.filter((url) => url.endsWith('/sesion')).length, 1);
  assert.equal(calls.filter((url) => url.endsWith('/conversacion')).length, 2);
  assert.equal(reactProps(input).disabled, false);
  assert.equal(reactProps(input).value, 'Y sin cebolla');
  history = { ...conversation(), mensajes: [...conversation().mensajes, persisted] };
  await act(async () => tick());
  assert.equal(elements(log, (node) => node.localName === 'li' && node.textContent.includes(persisted.texto)).length, 1);
});

test('actualización consulta más seguido al esperar, desacelera en reposo y nunca superpone consultas', async (t) => {
  const history = deferred();
  let reads = 0;
  let pending = false;
  globalThis.fetch = async (url) => {
    if (!url.endsWith('/conversacion')) return response({});
    reads += 1;
    if (reads === 3) return history.promise;
    return response(pending ? { ...conversation(), mensajes: [{ id: 'pendiente', direccion: 'cliente', estado: 'PENDIENTE', texto: 'Hola', creado_en: new Date().toISOString() }] } : conversation());
  };
  await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const idleDelay = scheduledDelay;
  pending = true;
  await act(async () => tick());
  assert.ok(scheduledDelay < idleDelay);
  const refresh = tick;
  await act(async () => { void refresh(); void refresh(); });
  assert.equal(reads, 3);
  pending = false;
  await act(async () => history.resolve(response(conversation())));
  assert.equal(reads, 4);
  assert.equal(scheduledDelay, idleDelay);
});

test('compositor conserva Mayús+Enter y composición, y Enter envía una sola solicitud', async (t) => {
  const calls = [];
  const sent = deferred();
  globalThis.fetch = async (url) => { calls.push(url); if (url.endsWith('/mensajes')) sent.resolve(); return response(url.endsWith('/conversacion') ? conversation() : url.endsWith('/mensajes') ? { id: 'teclado', estado: 'PENDIENTE' } : {}); };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: 'Mi pedido\nsin tomate' } }));
  let prevented = 0;
  const event = { key: 'Enter', shiftKey: true, nativeEvent: {}, preventDefault() { prevented += 1; } };
  await act(async () => reactProps(input).onKeyDown(event));
  await act(async () => reactProps(input).onKeyDown({ ...event, shiftKey: false, nativeEvent: { isComposing: true } }));
  assert.equal(prevented, 0);
  assert.equal(calls.filter((url) => url.endsWith('/mensajes')).length, 0);
  await act(async () => { reactProps(input).onKeyDown({ ...event, shiftKey: false }); await sent.promise; });
  assert.equal(prevented, 1);
  assert.equal(calls.filter((url) => url.endsWith('/mensajes')).length, 1);
});

test('reintentar un envío incierto no borra el borrador escrito mientras esperaba el acuse', async (t) => {
  const failed = deferred();
  const started = deferred();
  const retried = deferred();
  const sent = [];
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/mensajes')) {
      sent.push(JSON.parse(options.body));
      if (sent.length === 1) { started.resolve(); return failed.promise; }
      retried.resolve();
      return response({ id: 'reintentado', estado: 'PENDIENTE' }, 202);
    }
    return response(url.endsWith('/conversacion') ? conversation() : {});
  };
  const container = await mount(t, ChatDrawer, { isOpen: true, onClose() {} });
  const input = elements(container, (node) => node.localName === 'textarea')[0];
  await act(async () => reactProps(input).onChange({ target: { value: 'Mensaje original' } }));
  await act(async () => { reactProps(elements(container, (node) => node.localName === 'form')[0]).onSubmit({ preventDefault() {} }); await started.promise; });
  await act(async () => reactProps(input).onChange({ target: { value: 'Mi siguiente consulta' } }));
  await act(async () => failed.reject(new Error('Respuesta perdida')));
  await act(async () => { reactProps(button(container, 'Reintentar mismo envío')).onClick(); await retried.promise; });
  assert.equal(reactProps(input).value, 'Mi siguiente consulta');
  assert.equal(sent[0].solicitud_id, sent[1].solicitud_id);
  assert.equal(sent[1].texto, 'Mensaje original');
});
