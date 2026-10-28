// Contrato de datos de Caja: catálogos de turnos, estados y métodos de pago,
// validadores de las respuestas de la API (consolidado y cierre) y formateadores
// de fechas contables, horas y dinero en pesos argentinos.
import { UserFacingError } from '../shared/api/userErrors.js';
// Etiquetas visibles para los códigos que devuelve la API.
export const TURNOS = { MEDIODIA: 'Mediodía', NOCHE: 'Noche' };
export const ESTADOS = { ABIERTO: 'Abierto', PENDIENTE_APROBACION: 'Pendiente de aprobación', APROBADO: 'Aprobado' };
export const METODOS = { EFECTIVO: 'Efectivo', MERCADO_PAGO: 'Mercado Pago', CUENTA_DNI: 'Cuenta DNI', NARANJA_X: 'Naranja X', OTRA_BILLETERA: 'Otra billetera', TRANSFERENCIA: 'Transferencia' };
// Validadores básicos de campos (enteros, ids, importes decimales y timestamps ISO).
const moneyFields = ['total_efectivo', 'total_billeteras', 'total_devoluciones', 'total_general'];
const integer = (value) => Number.isSafeInteger(value) && value >= 0;
const id = (value) => Number.isSafeInteger(value) && value > 0;
const amount = (value) => (typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value) || typeof value === 'number') && Number.isFinite(Number(value));
const timestamp = (value) => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d/.test(value) && Number.isFinite(Date.parse(value));

// Fechas contables son valores civiles, nunca instantes UTC.
export function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}
// Valida la selección de consolidado: turno actual o una fecha y turno concretos.
export function validateSelection(selection) {
  if (selection.mode === 'actual') return;
  if (selection.mode !== 'specific' || !validDate(selection.fecha)) throw new UserFacingError('Ingresá una fecha contable real (AAAA-MM-DD).');
  if (!Object.hasOwn(TURNOS, selection.turno)) throw new UserFacingError('Seleccioná un turno válido.');
}
// Valida los filtros del historial (fechas reales, rango ordenado y estado conocido).
export function validateFilters({ desde = '', hasta = '', estado = '' }) {
  if (desde && !validDate(desde) || hasta && !validDate(hasta)) throw new UserFacingError('Ingresá fechas reales para el historial.');
  if (desde && hasta && desde > hasta) throw new UserFacingError('El rango es inválido: Hasta debe ser igual o posterior a Desde.');
  if (estado && !Object.hasOwn(ESTADOS, estado)) throw new UserFacingError('Seleccioná un estado válido.');
}
// Comprueba que un consolidado de turno tenga todos los campos con el formato esperado.
export function consolidadoValido(data) {
  return Boolean(data && validDate(data.fecha) && Object.hasOwn(TURNOS, data.turno)
    && timestamp(data.desde) && timestamp(data.hasta)
    && [...moneyFields, 'total_propinas'].every((key) => amount(data[key]))
    && ['cantidad_pedidos', 'cantidad_pagos', 'pagos_pendientes_conciliacion'].every((key) => integer(data[key]))
    && Array.isArray(data.desglose_metodos) && data.desglose_metodos.every((item) => item && Object.hasOwn(METODOS, item.metodo_pago) && amount(item.total) && integer(item.cantidad)));
}
// Comprueba que un cierre de caja sea coherente (un cierre aprobado debe tener aprobador y fecha).
export function cierreValido(data) {
  return Boolean(data && id(data.id) && validDate(data.fecha) && Object.hasOwn(TURNOS, data.turno)
    && Object.hasOwn(ESTADOS, data.estado) && timestamp(data.abierto_en)
    && (data.cerrado_en === null || timestamp(data.cerrado_en))
    && (data.aprobado_en === null || timestamp(data.aprobado_en))
    && (data.generado_por === null || id(data.generado_por)) && (data.aprobado_por === null || id(data.aprobado_por))
    && (data.observaciones === null || typeof data.observaciones === 'string')
    && moneyFields.every((key) => amount(data[key])) && integer(data.cantidad_pedidos)
    && (data.estado !== 'APROBADO' || id(data.aprobado_por) && timestamp(data.aprobado_en)));
}
// Devuelve los datos si pasan el validador; si no, lanza un error visible para el usuario.
export function checked(data, valid) {
  if (!valid(data)) throw new UserFacingError('No pudimos confirmar la operación. Comprobá su estado antes de reintentar.');
  return data;
}
// Indica si dos registros corresponden a la misma fecha contable y turno.
export const sameTarget = (a, b) => a?.fecha === b?.fecha && a?.turno === b?.turno;
export const formatDate = (date) => validDate(date) ? date.split('-').reverse().join('/') : '—';
// Formatea un timestamp de la API para mostrarlo en hora de Argentina.
export function formatTimestamp(value) {
  if (!value) return '—';
  // Los offsets se convierten a la zona del negocio; un legado sin offset se
  // muestra literalmente como hora del servidor, sin inventar su zona.
  if (!/(Z|[+-]\d\d:\d\d)$/.test(value)) return `${formatDate(value.slice(0, 10))} ${value.slice(11, 19)} (hora del servidor)`;
  return `${new Intl.DateTimeFormat('es-AR', { timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))} (Argentina)`;
}
// Formatea un importe en pesos argentinos.
export const formatMoney = (value) => new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' }).format(Number(value));
// Huella del cierre para detectar si otra persona lo modificó mientras se revisaba.
export const fingerprint = (cierre) => JSON.stringify(cierre);
