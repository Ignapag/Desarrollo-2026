const formatoFecha = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit',
});
const formatoDia = new Intl.DateTimeFormat('es-AR', {
  timeZone: 'UTC', weekday: 'short', day: 'numeric',
});

// Rechazar respuestas incompletas antes de que alcancen los gráficos o las tablas.
export function validarReportes(resumen, ventas, rentabilidad) {
  const filas = (lista, campos) => Array.isArray(lista) && lista.every((fila) => fila && campos.every((campo) => ['string', 'number'].includes(typeof fila[campo])));
  const valido = resumen && Number.isFinite(Date.parse(resumen.actualizado_en))
    && ['pedidos_dia', 'pedidos_semana', 'pedidos_mes'].every((campo) => Number.isFinite(resumen[campo]))
    && filas(resumen.ranking_productos, ['producto_id', 'producto', 'cantidad_vendida', 'ranking'])
    && Array.isArray(resumen.alertas_stock)
    && ((resumen.ingreso_neto_confirmado === undefined && resumen.ingresos_por_metodo === undefined)
      || filas(resumen.ingresos_por_metodo, ['metodo_pago', 'ingreso_neto']))
    && filas(ventas, ['periodo', 'producto_id', 'producto', 'cantidad_vendida'])
    && ventas.every((fila) => /^\d{4}-\d{2}-\d{2}$/.test(fila.periodo) && Number.isFinite(Date.parse(`${fila.periodo}T12:00:00Z`)))
    && (rentabilidad === undefined || filas(rentabilidad, ['producto_id', 'producto', 'unidades_vendidas', 'ingreso_estimado', 'costo_estimado', 'margen_estimado', 'porcentaje_margen']));
  if (!valido) throw new Error('Respuesta de reportes incompleta');
}

export function periodoPanel(ahora = new Date()) {
  const partes = Object.fromEntries(formatoFecha.formatToParts(ahora).map(({ type, value }) => [type, value]));
  const hoy = new Date(`${partes.year}-${partes.month}-${partes.day}T12:00:00Z`);
  const dias = Array.from({ length: 7 }, (_, indice) => {
    const dia = new Date(hoy);
    dia.setUTCDate(dia.getUTCDate() - 6 + indice);
    return { fecha: dia.toISOString().slice(0, 10), nombre: formatoDia.format(dia) };
  });
  return { desde: dias[0].fecha, hasta: dias[6].fecha, dias };
}

export function unidadesPorDia(dias, ventas) {
  const totales = new Map(dias.map(({ fecha }) => [fecha, 0]));
  for (const venta of ventas) {
    if (totales.has(venta.periodo)) {
      totales.set(venta.periodo, totales.get(venta.periodo) + Number(venta.cantidad_vendida));
    }
  }
  return dias.map((dia) => ({ ...dia, unidades: totales.get(dia.fecha) }));
}
