import { apiFetch } from '../shared/api/http';

const attempts = new Map();
const postHeaders = { 'X-Chat-Demo': '1' };
const prefix = '/api/chat-demo';
let sessionInitialization;

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
}

async function sendJson(kind, path, content) {
  const attempt = await attemptId(kind, JSON.stringify(content));
  const result = await apiFetch(`${prefix}/${path}`, {
    method: 'POST', headers: postHeaders,
    body: JSON.stringify({ solicitud_id: attempt.id, ...content }),
  });
  finishAttempt(attempt.key);
  return result;
}

export const getChatConfig = () => apiFetch(`${prefix}/config`);
export const getChatConversation = () => apiFetch(`${prefix}/conversacion`);
export async function openChatSession() {
  sessionInitialization ||= apiFetch(`${prefix}/sesion`, { method: 'POST', headers: postHeaders, body: '{}' })
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
  const result = await apiFetch(`${prefix}/comprobantes`, {
    method: 'POST', body: file,
    headers: { ...postHeaders, 'Content-Type': file.type, 'X-Solicitud-Id': attempt.id },
  });
  finishAttempt(attempt.key);
  return result;
}

export function chatMessageStatus(message) {
  if (message.direccion === 'cliente') return message.estado === 'PROCESADO' ? 'Procesado' : 'Pendiente de procesamiento';
  return ({ PENDIENTE: 'Pendiente de envío simulado', ENVIANDO: 'Procesando envío simulado', SIMULADO: 'Disponible en la demo', FALLIDO: 'Falló el envío simulado', INCIERTO: 'Envío simulado por revisar' })[message.estado] || message.estado;
}
