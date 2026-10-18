const formatoFecha = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit',
});
const formatoDia = new Intl.DateTimeFormat('es-AR', {
  timeZone: 'UTC', weekday: 'short', day: 'numeric',
});

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
