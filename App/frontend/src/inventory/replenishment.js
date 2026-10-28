// Cálculos de reposición manual de stock: interpretación de cantidades, plan de
// reposición con saldo resultante y formateo de cantidades con su unidad.
import { UserFacingError } from '../shared/api/userErrors.js';

// Reglas locales de reposición manual. La API vuelve a validar cantidad, permiso y saldo.
// Se calcula en milésimas con BigInt para no arrastrar errores de punto flotante.
const SCALE = 1000n;
const MAX_SCALED = 999999999999n; // NUMERIC(12,3) en ingrediente.cantidad_actual
const invalid = (error) => ({ valid: false, error });

// Desde estas cantidades se muestra el resumen y se pide confirmar antes de enviar.
export const LARGE_REPLENISHMENT = { UNIDAD: 200, GR: 5000, ML: 5000, KG: 50, LT: 50 };

// Interpreta la cantidad escrita (coma decimal, hasta 3 decimales) y la convierte a milésimas.
export function parseReplenishQuantity(value) {
  const text = String(value ?? '').trim();
  if (!text) return invalid('Ingresá la cantidad a reponer.');
  if (text.startsWith('-')) return invalid('La cantidad debe ser mayor que cero.');
  // En es-AR "2.500" se lee como dos mil quinientos; en otros formatos, como 2,5.
  if (/^[1-9]\d{0,2}\.\d{3}$/.test(text)) return invalid('No queda claro si es un millar o un decimal. Escribí los miles sin punto (2500) y los decimales con coma (2,5).');
  const match = /^(\d+)(?:[.,](\d+))?$/.exec(text);
  if (!match) return invalid('Escribí solo números, por ejemplo 2500 o 2,5.');
  const [, integer, decimals = ''] = match;
  if (decimals.length > 3) return invalid('Usá como máximo 3 decimales.');
  if (integer.replace(/^0+(?=\d)/, '').length > 9) return invalid('La cantidad supera el máximo permitido.');
  const scaled = BigInt(integer) * SCALE + BigInt(decimals.padEnd(3, '0'));
  if (scaled < 1n) return invalid('La cantidad debe ser mayor que cero.');
  // "2,500" es 2,5 en es-AR, pero puede ser un millar escrito en otro formato: se confirma.
  const review = /^[1-9]\d{0,2},\d{3}$/.test(text);
  return { valid: true, scaled, amount: scaledToAmount(scaled), review, error: '' };
}

// La reposición no es idempotente: ante cualquier duda no se reenvía sin una confirmación explícita.
export const isUncertainReplenishment = (error) => !(error instanceof UserFacingError) || error.uncertain;

// Plan de reposición: cantidad válida, saldo resultante y si supera el umbral de "grande".
export function replenishmentPlan(item, value) {
  const parsed = parseReplenishQuantity(value);
  if (!parsed.valid) return parsed;
  if (!Number.isFinite(item?.stock) || item.stock < 0) return invalid('Actualizá el inventario antes de reponer.');
  const resulting = toScaled(item.stock) + parsed.scaled;
  if (resulting > MAX_SCALED) return invalid('Con esa cantidad el stock superaría el máximo permitido.');
  const threshold = BigInt(LARGE_REPLENISHMENT[item.category] ?? LARGE_REPLENISHMENT.UNIDAD) * SCALE;
  return { ...parsed, resulting, large: parsed.scaled >= threshold };
}

// Texto del resumen que se pide confirmar.
export function replenishmentSummary(item, plan) {
  return `Vas a sumar ${scaledWithUnit(plan.scaled, item.category)} a ${item.name}; quedará en ${scaledWithUnit(plan.resulting, item.category)}.`;
}

// Unidad visible del insumo (singular/plural para unidades).
export const unitLabel = (unit, scaled = SCALE) => unit === 'UNIDAD' || !unit
  ? (scaled === SCALE ? 'unidad' : 'unidades')
  : ({ GR: 'g', KG: 'kg', LT: 'l', ML: 'ml' })[unit] || unit;

// Convierte cantidades a milésimas y las formatea con separador de miles y coma decimal.
export const toScaled = (number) => BigInt(Math.round(number * 1000));

export function formatScaled(scaled) {
  const integer = (scaled / SCALE).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const decimals = String(scaled % SCALE).padStart(3, '0').replace(/0+$/, '');
  return decimals ? `${integer},${decimals}` : integer;
}

export const formatQuantity = (number) => Number.isFinite(number) ? formatScaled(toScaled(number)) : '—';
export const scaledWithUnit = (scaled, unit) => `${formatScaled(scaled)} ${unitLabel(unit, scaled)}`;
export const quantityWithUnit = (number, unit) => Number.isFinite(number) ? scaledWithUnit(toScaled(number), unit) : '—';

// Milésimas a texto decimal con punto para enviar a la API.
function scaledToAmount(scaled) {
  const decimals = String(scaled % SCALE).padStart(3, '0').replace(/0+$/, '');
  return `${scaled / SCALE}${decimals ? `.${decimals}` : ''}`;
}
