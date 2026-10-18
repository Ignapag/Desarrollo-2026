export const ORDER_STATES = [
  ['PENDIENTE', 'Nuevos'], ['CONFIRMADO', 'Confirmados'],
  ['EN_PREPARACION', 'En preparación'], ['LISTO', 'Listos'],
  ['EN_CAMINO', 'En camino'], ['ENTREGADO', 'Entregados'], ['CANCELADO', 'Cancelados'],
];
export const stateLabel = (state) => ORDER_STATES.find(([id]) => id === state?.toUpperCase())?.[1] || state || 'Sin informar';
export const isStaff = (role) => ['EMPLEADO', 'ADMINISTRADOR', 'DUENIO'].includes(role);
export const isPrivileged = (role) => ['ADMINISTRADOR', 'DUENIO'].includes(role);
export const isClosed = (order) => ['ENTREGADO', 'CANCELADO'].includes(order.estado);
export const hasAssignment = (order) => Boolean(order.envio?.viaje_id && order.envio?.repartidor_id
  && ['PLANIFICADO', 'EN_RUTA'].includes(order.envio?.estado_viaje));
export const canEditOperation = (order, role) => isStaff(role)
  && ['PENDIENTE', 'CONFIRMADO', 'EN_PREPARACION', 'LISTO'].includes(order.estado) && !hasAssignment(order);

export function addressLabel(address) {
  return address ? [address.calle, address.numero, address.localidad].filter(Boolean).join(', ') : 'Dirección no disponible';
}
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
    items: (order.items || []).map((item) => `${item.cantidad}x ${item.nombre_producto}${item.aclaraciones ? ` · ${item.aclaraciones}` : ''}`),
    date: order.creado_en,
  };
}
export const money = (value) => value != null && Number.isFinite(Number(value))
  ? Number(value).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }) : 'No disponible';
export const dateTime = (value) => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('es-AR') : 'No registrado';
export function ageMinutes(value, now = Date.now()) {
  const start = Date.parse(value);
  return Number.isFinite(start) ? Math.max(0, Math.floor((now - start) / 60000)) : null;
}

// Solo ofrece comandos compatibles con el estado físico conocido. La API vuelve a validarlos.
export function stateCommands(order, role) {
  if (!isStaff(role) || hasAssignment(order)) return [];
  const commands = [];
  const add = (estado, label, extra = {}) => commands.push({ estado, label, ...extra });
  if (order.estado === 'PENDIENTE') add('CONFIRMADO', 'Confirmar pedido');
  if (['PENDIENTE', 'CONFIRMADO'].includes(order.estado)) add('EN_PREPARACION', 'Enviar a cocina');
  if (order.estado === 'EN_PREPARACION') add('LISTO', 'Marcar listo');
  if (['CONFIRMADO', 'EN_PREPARACION'].includes(order.estado)) add('PENDIENTE', 'Corregir a pendiente (conservar insumos)', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  if (order.estado === 'EN_PREPARACION') add('CONFIRMADO', 'Corregir a confirmado (conservar insumos)', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  if (order.estado === 'LISTO' && order.tipo_entrega === 'RETIRO') add('ENTREGADO', 'Registrar retiro entregado');
  if (order.estado === 'LISTO') add('EN_PREPARACION', 'Volver a preparación', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  if (!isClosed(order) && order.estado !== 'EN_CAMINO') {
    const cooked = Boolean(order.preparacion_en) || ['EN_PREPARACION', 'LISTO'].includes(order.estado);
    add('CANCELADO', cooked ? 'Cancelar y declarar merma' : 'Cancelar y devolver reserva', {
      correccion: cooked, ...(cooked ? { tratamiento_stock: 'MERMA' } : {}),
    });
  }
  if (isClosed(order) && isPrivileged(role)) {
    add('EN_PREPARACION', 'Reabrir y consumir insumos nuevamente', { correccion: true, tratamiento_stock: 'RECONSUMIR' });
    if (order.estado === 'ENTREGADO' && !(order.tipo_entrega === 'DELIVERY' && order.envio?.viaje_id)) add('LISTO', 'Corregir entrega a listo (conservar insumos)', { correccion: true, tratamiento_stock: 'CONSERVAR' });
  }
  return commands;
}

export function ordersPath({ q = '', estado = '', activos, cliente_id } = {}) {
  const query = new URLSearchParams();
  if (q.trim()) query.set('q', q.trim());
  if (estado) query.set('estado', estado);
  if (activos != null) query.set('activos', String(activos));
  if (cliente_id != null) query.set('cliente_id', String(cliente_id));
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

export function confirmedOrder(result, id) {
  const candidate = result?.pedido || result;
  return candidate && (id == null || candidate.id === id) && Number.isInteger(candidate.version)
    && candidate.numero != null && Array.isArray(candidate.items) && Array.isArray(candidate.historial)
    && ORDER_STATES.some(([state]) => state === candidate.estado) ? candidate : null;
}
