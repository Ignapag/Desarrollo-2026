export function createOrderCommands(http) {
  const send = (path, body, method = 'POST') => http(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) });
  return {
    detail: (id, signal) => http(`/api/pedidos/${id}`, { signal }),
    edit: (order, changes, motivo) => send(`/api/pedidos/${order.id}/operacion`, { ...changes, motivo, version_esperada: order.version }, 'PATCH'),
    state: (order, command, motivo) => {
      const { estado, correccion, tratamiento_stock } = command;
      return send(`/api/pedidos/${order.id}/estado`, {
        estado, motivo, version_esperada: order.version, estado_esperado: order.estado,
        ...(correccion ? { correccion } : {}), ...(tratamiento_stock ? { tratamiento_stock } : {}),
      }, 'PATCH');
    },
    riders: (signal) => http('/api/delivery/repartidores', { signal }),
    trips: (signal) => http('/api/delivery/viajes', { signal }),
    trip: (id, signal) => http(`/api/delivery/viajes/${id}`, { signal }),
    assign: (id, repartidor_id, motivo) => send(`/api/delivery/pedidos/${id}/asignar`, { repartidor_id, motivo }),
    shipment: (id, action, body) => send(`/api/delivery/envios/${id}/${action}`, body),
    startTrip: (id) => send(`/api/delivery/viajes/${id}/iniciar`),
    financial: (id, signal) => http(`/api/pagos/pedido/${id}/estado`, { signal }),
    reconcile: (id) => send(`/api/pagos/${id}/conciliar`, {}),
  };
}

// Se conserva contenido y UUID incluso si se pierde la respuesta del primer POST.
export function createPaymentAttempt(body, kind, uuid = () => crypto.randomUUID()) {
  return { kind, body: { ...body, clave_operacion: uuid() } };
}

export async function executePayment(http, attempt) {
  const post = (path, body) => http(path, { method: 'POST', body: JSON.stringify(body) });
  const result = await post(`/api/pagos/${attempt.kind}`, attempt.body);
  if (attempt.kind === 'transferencia' && result.estado !== 'CONCILIADO') {
    try {
      return await post(`/api/pagos/${result.id}/conciliar`, {});
    } catch (error) {
      throw new Error(`La transferencia quedó registrada para revisión. No registres otro cobro: reintentá esta operación o conciliá el pendiente. ${error.message}`);
    }
  }
  return result;
}
