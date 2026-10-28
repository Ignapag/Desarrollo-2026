// Cliente HTTP único del frontend: llama a la API con la cookie de sesión, aplica un
// tiempo máximo, traduce errores a mensajes para el usuario, marca como "inciertas" las
// escrituras sin respuesta y avisa a la app cuando la sesión venció (401).
import { UserFacingError, apiResponseError, CHECK_OPERATION_MESSAGE } from './userErrors';

// Base de la API (vacía = mismo origen, vía proxy), revisión de sesión y oyentes de 401.
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
let sessionRevision = 0;
const unauthorizedListeners = new Set();

// Invalida las respuestas de peticiones iniciadas antes de un cambio de sesión.
export function invalidateApiSession() { sessionRevision += 1; }
// Registra un oyente que se ejecuta cuando la API responde 401 fuera de /api/auth.
export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

/**
 * Hace una petición JSON a la API. Opciones extra: `signal` (cancelación) y `timeoutMs`
 * (30 s por defecto). Devuelve el cuerpo JSON (o null en 204) y lanza UserFacingError ante fallos.
 */
export async function apiFetch(path, options = {}) {
  const { signal, timeoutMs = 30000, ...requestOptions } = options;
  const write = !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase());
  const revision = sessionRevision;
  const controller = new AbortController();
  const cancel = () => controller.abort(signal.reason);
  if (signal?.aborted) cancel();
  else signal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => controller.abort(new UserFacingError(`Se agotó el tiempo de espera.${write ? ` ${CHECK_OPERATION_MESSAGE}` : ' Intentá nuevamente.'}`, { kind: 'timeout', uncertain: write })), timeoutMs);
  // La petición se corta si se cancela externamente o vence el tiempo máximo.
  let abortListener;
  const aborted = new Promise((_, reject) => {
    abortListener = () => reject(controller.signal.reason);
    if (controller.signal.aborted) abortListener();
    else controller.signal.addEventListener('abort', abortListener, { once: true });
  });
  try {
    return await Promise.race([aborted, (async () => {
      controller.signal.throwIfAborted();
      const response = await fetch(`${API_BASE}${path}`, {
        credentials: 'include',
        ...requestOptions,
        signal: controller.signal,
        headers: {
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...options.headers,
        },
      });

      let body;
      let validJson = true;
      if (response.status !== 204) {
        try { body = await response.json(); } catch { validJson = false; }
      }
      controller.signal.throwIfAborted();
      if (revision !== sessionRevision) throw new UserFacingError(`La sesión cambió. Volvé a ingresar.${write ? ` ${CHECK_OPERATION_MESSAGE}` : ''}`, { uncertain: write });
      if (!response.ok) {
        const error = apiResponseError(response.status, body, { path, write });
        if (response.status === 401 && !path.startsWith('/api/auth/')) {
          for (const listener of unauthorizedListeners) listener();
        }
        throw error;
      }
      if (response.status === 204) return null;
      if (!validJson || body === null || typeof body !== 'object') throw new UserFacingError(write ? CHECK_OPERATION_MESSAGE : 'No pudimos cargar la información. Intentá nuevamente.', { kind: 'request', uncertain: write });
      return body;
    })()]);
  } catch (error) {
    if (error instanceof UserFacingError) throw error;
    if (signal?.aborted && error?.name === 'AbortError') throw error;
    // No guardar la excepción original: podría contener cuerpos, URLs o secretos.
    throw new UserFacingError(`No pudimos conectar. Revisá tu conexión.${write ? ` ${CHECK_OPERATION_MESSAGE}` : ' Intentá nuevamente.'}`, { kind: 'connection', uncertain: write });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
    controller.signal.removeEventListener('abort', abortListener);
  }
}
