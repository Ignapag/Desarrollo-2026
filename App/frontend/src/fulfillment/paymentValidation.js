// Coincide con Decimal(max_digits=12, decimal_places=2) de los contratos de pagos.
// No se redondea dinero ni se interpretan separadores de miles ambiguos.
export function paymentAmount(value) {
  const normalized = String(value).trim().replace(',', '.');
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
  const integer = normalized.split('.')[0].replace(/^0+/, '') || '0';
  if (integer.length > 10 || Number(normalized) <= 0) return null;
  return normalized;
}
