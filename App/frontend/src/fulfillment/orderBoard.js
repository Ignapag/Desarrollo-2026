// Modelo del tablero de pedidos: agrupa por estado (separando los pagados de los
// nuevos), ordena, calcula esperas y alertas visuales y expone utilidades de
// presentación (resúmenes, etiquetas y media query del tablero).
import { useCallback, useSyncExternalStore } from 'react';
import { ORDER_STATES, ageMinutes, hasPaymentDebt, isOrderPaid } from './orderModel';

// Estados finales: el pedido ya no está en operación (historial).
export const CLOSED_STATES = ['ENTREGADO', 'CANCELADO'];
// Referencia visual del tablero, no una regla de la API: resalta esperas largas desde la creación.
export const LONG_WAIT_MINUTES = 30;

// Grupos de gestión: no son estados que se envíen a la API ni cambian cocina.
export const ORDER_GROUPS = [['PENDIENTE', 'Nuevos'], ['PAGADOS', 'Pagados'], ['POR_COBRAR', 'Por cobrar'],
  ...ORDER_STATES.filter(([id]) => !['PENDIENTE', 'CONFIRMADO'].includes(id))];
// Grupo del tablero de un pedido: los pendientes/confirmados se dividen según estén pagados.
export const orderGroup = (order) => order.estado === 'ENTREGADO' && hasPaymentDebt(order) ? 'POR_COBRAR'
  : ['PENDIENTE', 'CONFIRMADO'].includes(order.estado)
  ? isOrderPaid(order) ? 'PAGADOS' : 'PENDIENTE' : order.estado;

// Grupos visibles según la vista: activos, historial o todos.
export const scopeStates = (scope) => ORDER_GROUPS.filter(([id]) => scope === 'history' ? CLOSED_STATES.includes(id) || id === 'POR_COBRAR'
  : scope === 'active' ? !CLOSED_STATES.includes(id) : true);

// Convierte una fecha a milisegundos (null si es inválida) y obtiene la fecha de cierre del pedido.
const timestamp = (value) => { const time = Date.parse(value); return Number.isFinite(time) ? time : null; };
export const closedAt = (order) => order.entregado_en || order.cancelado_en || order.date;
// Las fechas desconocidas quedan al final; el número desempata para que el orden no salte.
const byTime = (left, right, direction) => left == null || right == null
  ? (left == null) - (right == null) : (left - right) * direction;

// Ordena: los cerrados del más reciente al más viejo; los activos por antigüedad (el más viejo primero).
export function sortOrders(orders, state) {
  const closed = CLOSED_STATES.includes(state) || state === 'POR_COBRAR';
  return [...orders].sort((a, b) => closed
    ? byTime(timestamp(closedAt(a)), timestamp(closedAt(b)), -1) || (b.number ?? 0) - (a.number ?? 0)
    : byTime(timestamp(a.date), timestamp(b.date), 1) || (a.number ?? 0) - (b.number ?? 0));
}

// Minutos de espera desde la creación (solo para pedidos abiertos).
export function waitMinutes(order, now) {
  return CLOSED_STATES.includes(order.estado) ? null : ageMinutes(order.date, now);
}
export const isLongWait = (minutes) => minutes != null && minutes >= LONG_WAIT_MINUTES;

// Fecha y hora corta para tarjetas del tablero.
export const shortDateTime = (value) => timestamp(value) == null ? 'Sin fecha'
  : new Date(value).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

// Formatea una espera en minutos, horas o días.
export function formatWait(minutes) {
  if (minutes == null) return 'Sin hora';
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`;
  return `${Math.floor(minutes / 1440)} d`;
}

// Avisos derivados de datos ya confirmados por la API; no reemplazan la revisión en el detalle.
export function orderAlerts(order, { now, pending = false } = {}) {
  const alerts = [];
  const closed = CLOSED_STATES.includes(order.estado);
  const saldo = Number(order.saldo_pendiente);
  if (pending) alerts.push({ id: 'pending', label: 'Operación en curso', tone: 'info' });
  const pendingTransfer = (order.pagos || []).some((payment) => payment.tipo === 'COBRO' && payment.estado === 'PENDIENTE' && payment.metodo_pago === 'TRANSFERENCIA');
  // Sólo un cobro pendiente es algo para revisar; sin él, una transferencia acordada aún no llegó
  // y cocina no puede empezar hasta conciliarla.
  if (!closed && pendingTransfer) alerts.push({ id: 'transfer', label: 'Transferencia por revisar', tone: 'warning' });
  else if (['PENDIENTE', 'CONFIRMADO'].includes(order.estado) && order.metodo_pago_acordado === 'TRANSFERENCIA' && saldo > 0) alerts.push({ id: 'transfer-wait', label: 'Espera transferencia', tone: 'info' });
  if (order.estado === 'ENTREGADO' && saldo > 0) alerts.push({ id: 'unpaid', label: 'Entregado con saldo', tone: 'danger' });
  if (order.estado === 'CANCELADO' && Number(order.neto_cobrado) > 0) alerts.push({ id: 'refund', label: 'Cobro a devolver', tone: 'danger' });
  if (isLongWait(waitMinutes(order, now))) alerts.push({ id: 'wait', label: 'Espera alta', tone: 'danger' });
  return alerts;
}

// Agrupa los pedidos por estado con su cantidad y cuántos tienen espera alta.
export function groupOrders(orders, states, now) {
  return Object.fromEntries(states.map(([id]) => {
    const list = sortOrders(orders.filter((order) => orderGroup(order) === id), id);
    return [id, { orders: list, count: list.length, longWait: list.filter((order) => isLongWait(waitMinutes(order, now))).length }];
  }));
}

// `compact` deja sólo la cantidad: en columnas angostas el detalle truncado no aporta.
export function itemsSummary(order, compact = false) {
  if (!order.items?.length) return 'Sin productos informados';
  const units = (order.detail?.items || []).reduce((sum, item) => sum + (Number(item.cantidad) || 0), 0);
  const count = units || order.items.length;
  const total = `${count} ${count === 1 ? 'producto' : 'productos'}`;
  return compact ? total : `${total} · ${order.items.join(', ')}`;
}

// Debajo de este ancho (con el menú lateral) cinco columnas no son legibles: se muestra un estado por vez.
export const BOARD_MEDIA = '(min-width: 1280px)';

// Hook que sigue una media query del navegador (p. ej. para cambiar el tablero a una columna).
export function useMediaQuery(query, fallback = true) {
  const subscribe = useCallback((notify) => {
    const media = window.matchMedia?.(query);
    media?.addEventListener('change', notify);
    return () => media?.removeEventListener('change', notify);
  }, [query]);
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(query).matches ?? fallback, () => fallback);
}

// Etiquetas accesibles con la cantidad de pedidos por estado.
export const countLabel = (count) => `${count} ${count === 1 ? 'pedido' : 'pedidos'}`;
export function stateSummaryLabel(label, summary, known) {
  if (!known) return `${label}: cantidad sin consultar`;
  return `${label}: ${countLabel(summary.count)}${summary.longWait ? `, ${summary.longWait} con ${LONG_WAIT_MINUTES} minutos o más de espera` : ''}`;
}
