const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
let sessionRevision = 0;
const unauthorizedListeners = new Set();

export function invalidateApiSession() { sessionRevision += 1; }
export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export async function apiFetch(path, options = {}) {
  const { signal, timeoutMs = 30000, ...requestOptions } = options;
  const revision = sessionRevision;
  const controller = new AbortController();
  const cancel = () => controller.abort(signal.reason);
  if (signal?.aborted) cancel();
  else signal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => controller.abort(new Error('Se agotó el tiempo de espera. Comprobá el estado de la operación antes de reintentar.')), timeoutMs);
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
      if (revision !== sessionRevision) throw new Error('La sesión cambió. Volvé a consultar los datos antes de continuar.');
      if (!response.ok) {
        const detail = body?.mensaje || body?.detail;
        const message = Array.isArray(detail) ? detail.map((item) => `${(item.loc || []).filter((part) => part !== 'body').join('.')}: ${item.msg || 'Valor inválido'}`).join('; ') : detail;
        const error = new Error(typeof message === 'string' ? message : `No se pudo completar la operación (HTTP ${response.status}).`);
        error.status = response.status;
        if (response.status === 401 && !path.startsWith('/api/auth/')) {
          for (const listener of unauthorizedListeners) listener();
        }
        throw error;
      }
      if (response.status === 204) return null;
      if (!validJson) throw new Error('El servidor no devolvió una respuesta válida. No pudimos confirmar la operación; comprobá su estado antes de reintentar.');
      return body;
    })()]);
  } catch (error) {
    if (error instanceof TypeError) throw new Error('No se pudo conectar con el servidor. Revisá la conexión y comprobá la operación antes de reintentar.', { cause: error });
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
    controller.signal.removeEventListener('abort', abortListener);
  }
}
