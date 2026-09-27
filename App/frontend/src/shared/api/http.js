const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.mensaje || body?.detail || 'No se pudo completar la operacion';
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return body;
}
