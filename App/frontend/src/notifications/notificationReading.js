// Estado de lectura de las notificaciones de un usuario, persistido en el navegador.
import { readNotificationKeys, saveNotificationKeys } from './notificationModel.js';

// Sólo claves de eventos por usuario; nunca mensajes, teléfonos ni datos de pago.
export function createNotificationReading(storage, userId) {
  let snapshot = { keys: readNotificationKeys(storage, userId), storageError: false };
  const listeners = new Set();
  const publish = (keys) => {
    if (keys.length === snapshot.keys.length && keys.every((key, index) => key === snapshot.keys[index])) return;
    snapshot = { keys, storageError: !saveNotificationKeys(storage, userId, keys) };
    for (const listener of listeners) listener();
  };
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    mark: (keys) => publish([...new Set([...snapshot.keys, ...keys])].slice(-500)),
    retainStock: (active) => publish(snapshot.keys.filter((key) => !key.startsWith('stock:') || active.has(key))),
  };
}
