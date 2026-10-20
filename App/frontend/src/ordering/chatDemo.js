import { apiFetch } from '../shared/api/http';

const attempts = new Map();
const postHeaders = { 'X-Chat-Demo': '1' };
const prefix = '/api/chat-demo';
const pendingKey = 'monu-chat-envio-pendiente';
const requestTimeout = 15000;
let sessionInitialization;
let pendingSend = null;
let storageUnavailable = false;

async function request(path, options = {}) {
  const controller = new AbortController();
  let timer;
  try {
    return await Promise.race([
      apiFetch(`${prefix}/${path}`, { ...options, signal: controller.signal }),
      new Promise((_, reject) => { timer = globalThis.setTimeout(() => {
        controller.abort();
        reject(new Error('El chat no respondió a tiempo. Volvé a intentar para comprobar el resultado.'));
      }, requestTimeout); }),
    ]);
  } catch (failure) {
    if (failure instanceof TypeError) throw new Error('No pudimos conectar con el chat. Revisá la conexión y reintentá.');
    throw failure;
  } finally {
    globalThis.clearTimeout(timer);
  }
}

// Sólo se conserva el envío sin confirmar en esta pestaña; el historial vive en el servidor.
export function getPendingChatSend() {
  if (storageUnavailable) return pendingSend;
  try {
    const saved = globalThis.sessionStorage?.getItem(pendingKey);
    if (globalThis.sessionStorage) pendingSend = saved ? JSON.parse(saved) : null;
  } catch { storageUnavailable = true; /* Almacenamiento bloqueado: conservar el intento en memoria. */ }
  return pendingSend;
}

function savePendingSend(value) {
  pendingSend = value;
  if (storageUnavailable) return;
  try {
    if (value) globalThis.sessionStorage?.setItem(pendingKey, JSON.stringify(value));
    else globalThis.sessionStorage?.removeItem(pendingKey);
  } catch { storageUnavailable = true; /* Sin almacenamiento: la recarga requerirá volver a escribir o elegir el archivo. */ }
}

function rememberSend(attempt, content) {
  const previous = getPendingChatSend();
  if (previous && previous.key !== attempt.key) throw new Error('Primero recuperá el envío anterior con el mismo contenido.');
  savePendingSend({ ...attempt, ...content });
}

export function reconcileChatSend(conversation) {
  const pending = getPendingChatSend();
  if (!pending || !conversation.mensajes?.some((message) => message.direccion === 'cliente' && message.id.endsWith(`:${pending.id}`))) return false;
  finishAttempt(pending.key);
  return true;
}

function confirmAttempt(attempt, result) {
  if (!result?.id || !['PENDIENTE', 'PROCESADO'].includes(result.estado)) throw new Error('No pudimos confirmar que el envío quedó guardado. Reintentá el mismo envío.');
  finishAttempt(attempt.key);
  return result;
}

async function sendAttempt(attempt, path, options) {
  try {
    return confirmAttempt(attempt, await request(path, options));
  } catch (failure) {
    // Un rechazo HTTP explícito permite corregir el contenido; una respuesta perdida exige replay.
    if (failure.status >= 400 && failure.status < 500 && getPendingChatSend()?.key === attempt.key) savePendingSend(null);
    throw failure;
  }
}

async function attemptId(kind, content) {
  const bytes = typeof content === 'string' ? new TextEncoder().encode(content) : await content.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  const key = `monu-chat-intento-${kind}-${hash}`;
  let id = attempts.get(key);
  try { id ||= globalThis.sessionStorage?.getItem(key); } catch { /* Navegación privada: conservar en esta pestaña. */ }
  id ||= crypto.randomUUID();
  attempts.set(key, id);
  try { globalThis.sessionStorage?.setItem(key, id); } catch { /* El backend conserva la conversación. */ }
  return { id, key };
}

function finishAttempt(key) {
  attempts.delete(key);
  try { globalThis.sessionStorage?.removeItem(key); } catch { /* Sin almacenamiento disponible. */ }
  if (getPendingChatSend()?.key === key) savePendingSend(null);
}

async function sendJson(kind, path, content) {
  const attempt = await attemptId(kind, JSON.stringify(content));
  const pending = getPendingChatSend();
  if (pending && pending.key !== attempt.key) throw new Error('Primero recuperá el envío anterior con el mismo contenido.');
  if (kind === 'texto') rememberSend(attempt, { text: content.texto });
  return sendAttempt(attempt, path, {
    method: 'POST', headers: postHeaders,
    body: JSON.stringify({ solicitud_id: attempt.id, ...content }),
  });
}

export const getChatConfig = () => request('config');
export async function getChatConversation() {
  const result = await request('conversacion');
  if (!Array.isArray(result?.mensajes) || !Array.isArray(result?.borradores)) throw new Error('No pudimos recuperar la conversación. Volvé a actualizarla.');
  return result;
}
export async function openChatSession() {
  sessionInitialization ||= request('sesion', { method: 'POST', headers: postHeaders, body: '{}' })
    .finally(() => { sessionInitialization = null; });
  await sessionInitialization;
  return getChatConversation();
}

export const sendChatDraft = (borrador) => sendJson('borrador', 'borradores', { borrador });
export async function sendChatText(value) {
  const texto = value.trim();
  if (!texto || texto.length > 2000) throw new Error('Escribí de 1 a 2000 caracteres.');
  return sendJson('texto', 'mensajes', { texto });
}

export async function sendChatReceipt(file) {
  if (!['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)) throw new Error('Elegí un archivo PDF, PNG o JPEG.');
  if (!file.size || file.size > 2 * 1024 * 1024) throw new Error('El comprobante debe pesar hasta 2 MiB y no estar vacío.');
  const attempt = await attemptId(`comprobante-${file.type}`, file);
  rememberSend(attempt, { fileName: file.name || 'comprobante', mime: file.type });
  return sendAttempt(attempt, 'comprobantes', {
    method: 'POST', body: file,
    headers: { ...postHeaders, 'Content-Type': file.type, 'X-Solicitud-Id': attempt.id },
  });
}

export function chatMessageStatus(message) {
  if (message.direccion === 'cliente') return ({ PROCESADO: 'Procesado', PENDIENTE: 'Guardado · pendiente de respuesta', FALLIDO: 'No se pudo procesar · requiere revisión' })[message.estado] || message.estado;
  return ({ PENDIENTE: 'Pendiente de envío simulado', ENVIANDO: 'Procesando envío simulado', SIMULADO: 'Disponible en la demo', FALLIDO: 'Falló el envío simulado', INCIERTO: 'Envío simulado por revisar' })[message.estado] || message.estado;
}
