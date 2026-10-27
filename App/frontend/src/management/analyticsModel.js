import { periodoPanel } from './datosPanel.js';

export const tarjeta = 'bg-monu-bone rounded-2xl p-4 sm:p-6 shadow-sm border border-monu-green/10 min-w-0';
const formatoFecha = new Intl.DateTimeFormat('es-AR', { timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric' });
export const fecha = (valor) => formatoFecha.format(new Date(`${valor}T12:00:00Z`));

export function periodoInicial(ahora = new Date()) {
  const hasta = periodoPanel(ahora).hasta;
  const inicio = new Date(`${hasta}T12:00:00Z`);
  inicio.setUTCDate(inicio.getUTCDate() - 29);
  return { desde: inicio.toISOString().slice(0, 10), hasta };
}

export function validarFechas({ desde, hasta }) {
  const valida = (valor) => /^\d{4}-\d{2}-\d{2}$/.test(valor)
    && valor.slice(0, 4) !== '0000'
    && !Number.isNaN(Date.parse(`${valor}T00:00:00Z`))
    && new Date(`${valor}T00:00:00Z`).toISOString().slice(0, 10) === valor;
  if (!valida(desde) || !valida(hasta)) return 'Completá ambas fechas con un día válido.';
  if (desde > hasta) return 'La fecha desde debe ser anterior o igual a la fecha hasta.';
  return '';
}
