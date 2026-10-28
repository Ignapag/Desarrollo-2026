import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import { useAuth } from '../auth/AuthContext';
import { can } from '../auth/permissions';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { createInboxResource } from './inboxResource';
import { inboxNotifications, sortNotifications, stockNotifications, validateInbox } from './notificationModel';

import { NotificationContext } from './notificationHooks';
import { createNotificationReading } from './notificationReading';
function browserStorage() { try { return window.localStorage; } catch { return null; } }

export function NotificationProvider({ children }) {
  const { user } = useAuth();
  const scope = user ? [user.id, user.backendRole, ...(user.permisos || [])].join(':') : 'visitante';
  return <NotificationSession key={scope} user={user}>{children}</NotificationSession>;
}

function NotificationSession({ user, children }) {
  const { state, refreshInventory } = useData();
  // La identidad de sesión, además del id, invalida respuestas de cuentas previas.
  const resource = useMemo(() => createInboxResource((signal) => {
    if (!can(user, 'whatsapp.ver')) return Promise.reject(Error('Sin permiso'));
    return apiFetch('/api/whatsapp/bandeja', { signal, cache: 'no-store', timeoutMs: 15000 });
  }, validateInbox), [user]);
  const inbox = useSyncExternalStore(resource.subscribe, resource.getSnapshot, resource.getSnapshot);
  const whatsappEnabled = can(user, 'whatsapp.ver');
  const stockEnabled = can(user, 'stock.ver');
  const reading = useMemo(() => createNotificationReading(browserStorage(), user?.id), [user?.id]);
  const { keys: readKeys, storageError } = useSyncExternalStore(reading.subscribe, reading.getSnapshot, reading.getSnapshot);
  const refreshInbox = useCallback((force = false, afterWrite = false) => {
    if (!whatsappEnabled) return Promise.reject(Error('Sin permiso'));
    if (afterWrite) resource.cancel();
    return resource.load(force);
  }, [resource, whatsappEnabled]);
  const refresh = useCallback(() => Promise.allSettled([
    ...(whatsappEnabled ? [refreshInbox(true)] : []),
    ...(stockEnabled ? [refreshInventory()] : []),
  ]), [whatsappEnabled, stockEnabled, refreshInbox, refreshInventory]);

  useEffect(() => {
    if (!whatsappEnabled && !stockEnabled) return undefined;
    const update = () => { if (!document.hidden) void refresh(); };
    update();
    const timer = window.setInterval(update, 8000);
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      resource.cancel();
      window.clearInterval(timer);
      window.removeEventListener('focus', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [refresh, resource, whatsappEnabled, stockEnabled]);

  const stock = useMemo(() => stockEnabled ? stockNotifications(state.inventory || []) : [], [stockEnabled, state.inventory]);
  const notifications = useMemo(() => sortNotifications([
    ...(whatsappEnabled ? inboxNotifications(inbox.data) : []), ...stock,
  ]), [whatsappEnabled, inbox.data, stock]);
  const stockKeys = JSON.stringify(stock.map((item) => item.key).sort());
  useEffect(() => {
    if (!stockEnabled || state.inventoryStatus !== 'ready') return;
    const active = new Set(JSON.parse(stockKeys));
    // Una recuperación confirmada permite avisar otra vez si vuelve a faltar stock.
    reading.retainStock(active);
  }, [stockEnabled, state.inventoryStatus, stockKeys, reading]);

  const markRead = (keys) => {
    const visible = new Set(notifications.map((item) => item.key));
    reading.mark(keys.filter((key) => visible.has(key)));
  };
  const read = new Set(readKeys);
  const items = notifications.map((item) => ({ ...item, read: read.has(item.key) }));
  const errors = [];
  if (whatsappEnabled && inbox.error) errors.push('No se pudieron actualizar los avisos de WhatsApp.');
  if (stockEnabled && state.inventoryStatus === 'error') errors.push('No se pudieron actualizar los avisos de inventario.');
  const loading = (whatsappEnabled && !inbox.data && !inbox.error) || (stockEnabled && ['idle', 'loading'].includes(state.inventoryStatus));
  return <NotificationContext.Provider value={{
    items, unreadCount: items.filter((item) => !item.read).length,
    loading, refreshing: inbox.loading, errors, storageError, refresh, refreshInbox, markRead,
    categoryStatus: {
      stock: { loading: stockEnabled && ['idle', 'loading'].includes(state.inventoryStatus),
        error: stockEnabled && state.inventoryStatus === 'error' ? 'No se pudieron actualizar los avisos de inventario.' : null },
      clientes: { loading: whatsappEnabled && !inbox.data && !inbox.error,
        error: whatsappEnabled && inbox.error ? 'No se pudieron actualizar los avisos de WhatsApp.' : null },
    },
    enabled: whatsappEnabled || stockEnabled,
    whatsappAvailable: whatsappEnabled && Boolean(inbox.data),
  }}>{children}</NotificationContext.Provider>;
}
