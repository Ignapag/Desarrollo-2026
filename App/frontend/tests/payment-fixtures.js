// Respuestas financieras con los campos del contrato real; no basta un ID aislado.
export function paymentFixture({ kind = 'efectivo', id = 51, orderId = 17, amount = '12000', received = amount, state = 'CONCILIADO', method = 'EFECTIVO', pedido } = {}) {
  const pago = { id, pedido_id: orderId, tipo: kind === 'devolucion' ? 'DEVOLUCION' : 'COBRO', metodo_pago: kind === 'transferencia' ? 'TRANSFERENCIA' : method, monto: amount, propina: '0', estado: state, cierre_caja_id: null, referencia_externa: null, registrado_por: 1, registrado_en: '2026-10-27T18:00:00Z', conciliado_en: state === 'CONCILIADO' ? '2026-10-27T18:00:00Z' : null, motivo: kind === 'devolucion' ? 'Devolución de prueba' : null };
  return kind === 'efectivo' ? { pago, detalle: { total_pedido: amount, monto_cobrado: amount, propina: '0', monto_recibido: received, vuelto: String(Number(received) - Number(amount)), saldo_restante: '0' }, ...(pedido ? { pedido } : {}) } : { ...pago, ...(pedido ? { pedido } : {}) };
}
