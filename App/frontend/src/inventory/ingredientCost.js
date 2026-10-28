// Validación y formato del costo unitario de un insumo (en pesos por unidad de medida).
// El costo se guarda como NUMERIC(12,2): hasta 10 enteros y 2 decimales, en ARS.
const money = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' });
const invalid = (error) => ({ valid: false, error });

// Etiquetas del costo por unidad del insumo (p. ej. "$ por KG").
export const costUnitLabel = (unit) => `$ por ${unit}`;

export const formatUnitCost = (cost, unit) => `${money.format(cost)} por ${unit}`;

// Interpreta el costo escrito por el usuario (coma o punto decimal, hasta 2 decimales)
// y devuelve `{ valid, amount, error }` con el importe normalizado para la API.
export function parseUnitCost(value) {
  const text = String(value ?? '').trim().replace(/^\$\s*/, '');
  if (!text) return invalid('Ingresá el costo. Usá 0 si todavía no lo conocés.');
  if (text.startsWith('-')) return invalid('El costo no puede ser negativo.');
  if (!/^\d+(?:[.,]\d+)?$/.test(text)) return invalid('Usá un importe como 4,50, sin separador de miles.');
  const [integer, decimals = ''] = text.replace(',', '.').split('.');
  if (decimals.length > 2) return invalid('Usá como máximo 2 decimales.');
  const whole = integer.replace(/^0+(?=\d)/, '');
  if (whole.length > 10) return invalid('El costo supera el máximo permitido.');
  const amount = decimals.replace(/0+$/, '') ? `${whole}.${decimals}` : whole;
  return { valid: true, amount, error: '' };
}
