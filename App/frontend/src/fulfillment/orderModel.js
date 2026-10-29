// Modelo de pedidos del frontend: estados y etiquetas, reglas de rol/edición,
// adaptación de pedidos de la API, cálculo de pagos exactos en centavos, comandos
// de estado permitidos y la "valla de frescura" que evita mostrar datos viejos.
import { extrasLabel } from '../ordering/ingredientExtras.js';
export const ORDER_STATES = [
  ['PENDIENTE', 'Nuevos'], ['CONFIRMADO', 'Confirmados'],
  ['EN_PREPARACION', 'En preparación'], ['LISTO', 'Listos'],
  ['EN_CAMINO', 'En camino'], ['ENTREGADO', 'Entregados'], ['CANCELADO', 'Cancelados'],
];
// Etiquetas visibles y reglas de rol/estado usadas por las pantallas de pedidos.
export const knownLabel = (labels, value, fallback = 'Sin informar') => typeof value === 'string' && Object.hasOwn(labels, value) ? labels[value] : fallback;
export const stateLabel = (state) => typeof state === 'string' ? ORDER_STATES.find(([id]) => id === state.toUpperCase())?.[1] || 'Sin informar' : 'Sin informar';
export const paymentMethodLabel = (method) => knownLabel({ EFECTIVO: 'Efectivo', TRANSFERENCIA: 'Transferencia', MERCADO_PAGO: 'Mercado Pago', CUENTA_DNI: 'Cuenta DNI', NARANJA_X: 'Naranja X', OTRA_BILLETERA: 'Otra billetera' }, method);
export const isStaff = (role) => ['EMPLEADO', 'ADMINISTRADOR', 'DUENIO'].includes(role);
export const isPrivileged = (role) => ['ADMINISTRADOR', 'DUENIO'].includes(role);
export const isClosed = (order) => ['ENTREGADO', 'CANCELADO'].includes(order.estado);
// Indica si el pedido tiene un repartidor asignado en un viaje planificado o en ruta.
export const hasAssignment = (order) => Boolean(order.envio?.viaje_id && order.envio?.repartidor_id
  && ['PLANIFICADO', 'EN_RUTA'].includes(order.envio?.estado_viaje));
// Un pedido se puede editar si el usuario tiene permiso, sigue en operación y no salió a reparto.
export const canEditOperation = (order, role, can = null) => (can ? can('pedidos.editar') : isStaff(role))
  && ['PENDIENTE', 'CONFIRMADO', 'EN_PREPARACION', 'LISTO'].includes(order.estado) && !hasAssignment(order);

// Dirección legible de un pedido delivery.
export function addressLabel(address) {
  return address ? [address.calle, address.numero, address.localidad].filter(Boolean).join(', ') : 'Dirección no disponible';
}
// Adapta un pedido de la API al formato usado por listas y tablero (conserva el original en `detail`).
export function mapOrder(order) {
  return {
    ...order,
    detail: order,
    number: order.numero,
    client: order.cliente,
    phone: order.telefono,
    address: order.tipo_entrega === 'RETIRO' ? 'Retiro en local' : addressLabel(order.direccion),
    status: order.estado.toLowerCase(),
    total: Number(order.total),
    items: (order.items || []).map((item) => `${item.cantidad}x ${item.nombre_producto}${item.aclaraciones ? ` · ${item.aclaraciones}` : ''}${item.extras?.length ? ` · ${extrasLabel(item.extras)}` : ''}`),
    date: order.creado_en,
  };
}
// Formateadores de dinero, fecha/hora y antigüedad en minutos.
export const money = (value) => value != null && Number.isFinite(Number(value))
  ? Number(value).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }) : 'No disponible';
export const dateTime = (value) => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('es-AR') : 'No registrado';
export function ageMinutes(value, now = Date.now()) {
  const start = Date.parse(value);
  return Number.isFinite(start) ? Math.max(0, Math.floor((now - start) / 60000)) : null;
}

// La clasificación usa importes confirmados por la API, en centavos exactos.
// Ausencia de saldo/neto no es prueba de pago; elegir efectivo tampoco lo es.
function paymentCents(value) {
  if (!['number', 'string'].includes(typeof value)) return null;
  const text = String(value);
  if (!/^-?[0-9]{1,15}(?:[.][0-9]{1,2})?$/.test(text)) return null;
  const negative = text.startsWith('-');
  const [whole, fraction = ''] = (negative ? text.slice(1) : text).split('.');
  const amount = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  return negative ? -amount : amount;
}
// Un pedido está pagado si lo cobrado cubre el total y no queda saldo pendiente.
export function isOrderPaid(order) {
  const total = paymentCents(order.total);
  const net = paymentCents(order.neto_cobrado);
  const balance = paymentCents(order.saldo_pendiente);
  return total !== null && total >= 0n && net !== null && net >= total
    && balance !== null && balance <= 0n;
}
// Los pendientes de cobro no se cierran por seleccionar una forma de pago.
export const allowsPickup = (order) => isOrderPaid(order);
export const hasPaymentDebt = (order) => {
  const balance = paymentCents(order.saldo_pendiente);
  return balance !== null && balance > 0n;
};
// La API de reparto informa el saldo conciliado, sin el desglose de pagos del pedido.
export function isShipmentPaid(shipment) {
  const total = paymentCents(shipment.total);
  const balance = paymentCents(shipment.saldo_pendiente);
  return total !== null && total >= 0n && balance !== null && balance <= 0n;
}

// Solo ofrece comandos compatibles con el estado físico conocido. La API vuelve a validarlos.
export function stateCommands(order, role, can = null) {
  if ((can ? !can('pedidos.cambiar_estado') && !can('pedidos.recuperar') : !isStaff(role)) || hasAssignment(order)) return [];
  const commands = [];
  const add = (estado, label, extra = {}) => commands.push({ estado, label, ...extra });
  if (order.estado === 'PENDIENTE') add('CONFIRMADO', 'Confirmar pedido');
  if (['PENDIENTE', 'CONFIRMADO'].includes(order.estado)) add('EN_PREPARACION', 'Enviar a cocina');
  if (order.estado === 'EN_PREPARACION') add('LISTO', 'Marcar listo');
  if (['CONFIRMADO', 'EN_PREPARACION'].includes(order.estado)) add('PENDIENTE', 'Corregir a pendiente (conservar insumos)', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  if (order.estado === 'EN_PREPARACION') add('CONFIRMADO', 'Corregir a confirmado (conservar insumos)', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  if (order.estado === 'LISTO' && order.tipo_entrega === 'RETIRO' && allowsPickup(order)) add('ENTREGADO', 'Registrar retiro entregado');
  if (order.estado === 'LISTO') add('EN_PREPARACION', 'Volver a preparación', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  if (!isClosed(order) && order.estado !== 'EN_CAMINO') {
    const cooked = Boolean(order.preparacion_en) || ['EN_PREPARACION', 'LISTO'].includes(order.estado);
    add('CANCELADO', cooked ? 'Cancelar y declarar merma' : 'Cancelar y devolver reserva', {
      correccion: cooked, ...(cooked ? { tratamiento_stock: 'MERMA' } : {}),
    });
  }
  if (isClosed(order) && (can ? can('pedidos.recuperar') : isPrivileged(role))) {
    add('EN_PREPARACION', 'Reabrir y consumir insumos nuevamente', { correccion: true, tratamiento_stock: 'RECONSUMIR' });
    if (order.estado === 'ENTREGADO' && !(order.tipo_entrega === 'DELIVERY' && order.envio?.viaje_id)) add('LISTO', 'Corregir entrega a listo (conservar insumos)', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  }
  return commands;
}

// Arma la ruta de listado de pedidos con búsqueda, estado, activos y cliente.
export function ordersPath({ q = '', estado = '', activos, cliente_id, finalizados_hoy = false } = {}) {
  const query = new URLSearchParams();
  if (q.trim()) query.set('q', q.trim());
  if (estado) query.set('estado', estado);
  if (activos != null) query.set('activos', String(activos));
  if (cliente_id != null) query.set('cliente_id', String(cliente_id));
  if (finalizados_hoy) query.set('finalizados_hoy', 'true');
  return `/api/pedidos${query.size ? `?${query}` : ''}`;
}

// Un GET iniciado antes o durante una mutación nunca puede restaurar una versión vieja.
export function createFreshnessFence() {
  let revision = 0;
  let sequence = 0;
  let pending = 0;
  return {
    read() { return { revision, sequence: ++sequence, blocked: pending > 0 }; },
    accepts(token) { return !token.blocked && !pending && token.revision === revision && token.sequence === sequence; },
    beginMutation() { revision += 1; pending += 1; },
    endMutation() { revision += 1; pending -= 1; },
    invalidate() { revision += 1; },
  };
}

// Devuelve el pedido si la respuesta de la API es un pedido completo y coincide con `id`; si no, null.
export function confirmedOrder(result, id) {
  const candidate = result?.pedido || result;
  return candidate && (id == null || candidate.id === id) && Number.isInteger(candidate.version)
    && candidate.numero != null && Array.isArray(candidate.items) && Array.isArray(candidate.historial)
    && ORDER_STATES.some(([state]) => state === candidate.estado) ? candidate : null;
}
