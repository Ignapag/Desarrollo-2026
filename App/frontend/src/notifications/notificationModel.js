// Modelo de notificaciones: validación de la bandeja de WhatsApp, conversión de
// comprobantes, atenciones y alertas de stock en avisos, orden por prioridad,
// tiempo transcurrido, persistencia de lecturas y categorías visibles.
const positiveId = (value) => Number.isSafeInteger(value) && value > 0;
const receiptStates = new Set(['PENDIENTE', 'APROBADO', 'RECHAZADO']);
const attentionReasons = new Set(['SOLICITUD', 'PROVEEDOR']);

// Valida la estructura mínima de la bandeja de WhatsApp.
export function validateInbox(data) {
  if (!['comprobantes', 'cambios', 'atenciones', 'salidas'].every((key) => Array.isArray(data?.[key]))
    || !data.comprobantes.every((item) => positiveId(item?.id) && positiveId(item.pedido_id) && receiptStates.has(item.estado))
    || !data.atenciones.every((item) => positiveId(item?.id) && typeof item.motivo === 'string' && item.estado === 'PENDIENTE')) {
    throw Error('Bandeja inválida');
  }
  return data;
}

// Fecha válida o null, y referencia visible del pedido.
const dateValue = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
const orderReference = (item) => positiveId(item.numero) ? 'Pedido #' + item.numero : positiveId(item.pedido_id) ? 'Pedido #' + item.pedido_id : null;

// Avisos de WhatsApp: comprobantes por verificar y atenciones que piden ayuda.
// Un comprobante revisado (aprobado o rechazado) ya no requiere acción y no genera aviso.
export function inboxNotifications(inbox) {
  if (!inbox) return [];
  const receipts = inbox.comprobantes.filter((item) => item.estado === 'PENDIENTE').map((item) => ({
    key: 'comprobante:' + item.id, kind: 'comprobante', priority: 1,
    title: 'Comprobante pendiente', reference: orderReference(item),
    description: 'Transferencia por verificar.',
    pending: true, date: dateValue(item.creado_en),
    target: 'whatsapp-comprobantes-' + item.id, action: 'Revisar comprobante',
    href: '/dashboard/orders?bandeja=comprobantes&aviso=whatsapp-comprobantes-' + item.id,
  }));
  const attentions = inbox.atenciones.filter((item) => item.motivo === 'COMPROBANTE' || attentionReasons.has(item.motivo)).map((item) => {
    const receipt = item.motivo === 'COMPROBANTE';
    return {
      key: 'atencion:' + item.id, kind: receipt ? 'comprobante' : 'atencion', priority: receipt ? 1 : 2,
      title: receipt ? 'Comprobante pendiente' : 'Cliente necesita ayuda',
      reference: orderReference(item) || 'Atención #' + item.id,
      description: receipt ? 'Comprobante sin pedido vinculado. Requiere revisión humana.' : 'Una conversación de WhatsApp requiere atención.',
      pending: true, date: dateValue(item.creado_en), target: 'whatsapp-atencion-' + item.id,
      action: receipt ? 'Revisar comprobante' : 'Abrir conversación',
      href: '/dashboard/orders?bandeja=' + (receipt ? 'comprobantes' : 'atenciones') + '&aviso=whatsapp-atencion-' + item.id,
    };
  });
  return [...receipts, ...attentions];
}

// Avisos de stock: insumos activos agotados o por debajo del mínimo.
export function stockNotifications(inventory) {
  return inventory.filter((item) => item.active !== false && ['SIN_STOCK', 'BAJO_UMBRAL'].includes(item.level)).map((item) => ({
    key: 'stock:' + item.id + ':' + item.level, kind: 'stock', priority: item.level === 'SIN_STOCK' ? 0 : 3,
    title: item.level === 'SIN_STOCK' ? item.name + ' agotado' : 'Stock bajo: ' + item.name,
    reference: item.name, description: item.level === 'SIN_STOCK' ? 'Sin existencias disponibles.' : 'El stock alcanz? el mínimo configurado.',
    pending: true, date: null, action: 'Abrir ingrediente',
    href: '/dashboard/inventory?ingrediente=' + item.id + '#ingrediente-' + item.id,
  }));
}

// Elimina duplicados y ordena por prioridad, luego del más reciente al más viejo.
export function sortNotifications(items) {
  const unique = new Map();
  for (const item of items) if (!unique.has(item.key)) unique.set(item.key, item);
  return [...unique.values()].sort((a, b) => a.priority - b.priority || (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0) || a.key.localeCompare(b.key));
}

// Texto "Hace X minutos/horas/días" para una fecha.
export function elapsedTime(date, now = Date.now()) {
  if (!date || !Number.isFinite(Date.parse(date))) return null;
  const minutes = Math.max(0, Math.floor((now - Date.parse(date)) / 60000));
  if (minutes === 0) return 'Hace menos de un minuto';
  if (minutes < 60) return 'Hace ' + minutes + (minutes === 1 ? ' minuto' : ' minutos');
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return 'Hace ' + hours + (hours === 1 ? ' hora' : ' horas');
  const days = Math.floor(hours / 24);
  return 'Hace ' + days + (days === 1 ? ' día' : ' días');
}

// Lectura y guardado de las claves leídas por usuario (máximo 500, solo claves válidas).
const validReadKey = (key) => typeof key === 'string' && /^(comprobante:[1-9][0-9]*|atencion:[1-9][0-9]*|stock:[1-9][0-9]*:(SIN_STOCK|BAJO_UMBRAL))$/.test(key);
const storageKey = (id) => 'monu.notifications.read.v1:' + id;
export function readNotificationKeys(storage, id) {
  if (!positiveId(id)) return [];
  try { const keys = JSON.parse(storage?.getItem(storageKey(id)) || '[]'); return Array.isArray(keys) ? [...new Set(keys.filter(validReadKey))].slice(-500) : []; }
  catch { return []; }
}
export function saveNotificationKeys(storage, id, keys) {
  if (!positiveId(id)) return false;
  try { storage?.setItem(storageKey(id), JSON.stringify([...new Set(keys.filter(validReadKey))].slice(-500))); return Boolean(storage); }
  catch { return false; }
}

// Categorías de notificaciones y el permiso que requiere cada una.
export const NOTIFICATION_CATEGORIES = [
  { id: 'stock', label: 'STOCK', permission: 'stock.ver' },
  { id: 'clientes', label: 'CLIENTES', permission: 'whatsapp.ver' },
];
const categoryByKind = { stock: 'stock', comprobante: 'clientes', atencion: 'clientes' };
export const notificationCategory = (item) => Object.hasOwn(categoryByKind, item.kind) ? categoryByKind[item.kind] : null;
// Cantidad de avisos sin leer de una categoría.
export function categoryUnreadCount(items, category) {
  return items.filter((item) => notificationCategory(item) === category && !item.read).length;
}
