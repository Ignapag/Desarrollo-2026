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
    reconcile: (id) => send(`/api/pagos/${id}/conciliar?incluir_pedido=true`, {}),
  };
}

// Se conserva contenido y UUID incluso si se pierde la respuesta del primer POST.
export function createPaymentAttempt(body, kind, uuid = () => crypto.randomUUID()) {
  return { kind, body: { ...body, clave_operacion: uuid() } };
}

function cents(value) {
  if (!['string', 'number'].includes(typeof value) || !/^\d+(?:\.\d{1,2})?$/.test(String(value))) return null;
  const result = Math.round(Number(value) * 100);
  return Number.isSafeInteger(result) && result >= 0 ? result : null;
}

function validatePayment(result, attempt, { reconciled = false, id } = {}) {
  const cash = attempt.kind === 'efectivo';
  const payment = cash ? result?.pago : result;
  const expectedAmount = cents(cash ? attempt.body.monto_a_pagar : attempt.body.monto);
  const expectedMethod = cash ? 'EFECTIVO' : attempt.kind === 'transferencia' ? 'TRANSFERENCIA' : attempt.body.metodo_pago;
  const states = !reconciled && ((cash && attempt.body.conciliar_inmediato === false) || attempt.kind === 'transferencia') ? ['PENDIENTE', 'CONCILIADO'] : ['CONCILIADO'];
  const valid = Number.isSafeInteger(payment?.id) && payment.id > 0 && (!id || payment.id === id)
    && payment.pedido_id === attempt.body.pedido_id && payment.tipo === (attempt.kind === 'devolucion' ? 'DEVOLUCION' : 'COBRO')
    && payment.metodo_pago === expectedMethod && states.includes(payment.estado)
    && expectedAmount !== null && expectedAmount > 0 && cents(payment.monto) === expectedAmount;
  if (!valid) throw new Error('No se pudo confirmar el resultado del pago. Reintentá la misma operación para verificarlo sin duplicarlo.');
  if (cash) {
    const detail = result.detalle;
    const received = cents(attempt.body.monto_recibido);
    const tip = cents(attempt.body.propina ?? '0');
    if (!detail || cents(detail.monto_cobrado) !== expectedAmount || cents(detail.monto_recibido) !== received || cents(detail.propina) !== tip
      || cents(detail.vuelto) !== received - expectedAmount - tip || cents(detail.saldo_restante) === null || cents(detail.total_pedido) === null) {
      throw new Error('No se pudo confirmar el desglose del cobro. Reintentá la misma operación para verificarlo sin duplicarlo.');
    }
  }
  return payment;
}

export async function executePayment(http, attempt, { operativa = false } = {}) {
  const post = (path, body) => http(path, { method: 'POST', body: JSON.stringify(body) });
  const query = operativa ? `?incluir_pedido=true${attempt.kind === 'transferencia' ? '&confirmar_ingreso=true' : ''}` : '';
  const result = await post(`/api/pagos/${attempt.kind}${query}`, attempt.body);
  validatePayment(result, attempt);
  if (attempt.kind === 'transferencia' && result.estado !== 'CONCILIADO') {
    try {
      const reconciled = await post(`/api/pagos/${result.id}/conciliar${operativa ? '?incluir_pedido=true' : ''}`, {});
      validatePayment(reconciled, attempt, { reconciled: true, id: result.id });
      return reconciled;
    } catch (error) {
      throw new Error(`La transferencia quedó registrada para revisión. No registres otro cobro: reintentá esta operación o conciliá el pendiente. ${error.message}`);
    }
  }
  return result;
}
