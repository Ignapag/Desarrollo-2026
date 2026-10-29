import { UserFacingError } from '../shared/api/userErrors.js';

const units = { GR: 'g', KG: 'kg', UNIDAD: 'unidad', LT: 'l', ML: 'ml' };
export const portionLabel = (extra) => `${Number(extra.cantidad_requerida).toLocaleString('es-AR', { maximumFractionDigits: 3 })} ${units[extra.unidad_medida] || extra.unidad_medida}`;
export const extrasLabel = (extras = []) => extras.map((extra) => `+${extra.cantidad} × ${extra.nombre} (${portionLabel(extra)} por extra)`).join(', ');

export function extrasForVariant(product, variant) {
  if (product.category === 'Dips Extra') return [];
  return (product.extraOptions || []).filter((extra) => (variant ? extra.variantes?.includes(variant) : !extra.variantes?.length));
}

export function buildCustomizedItem(product, variantName, removed, quantities) {
  const options = extrasForVariant(product, variantName);
  const extras = [];
  for (const [id, quantity] of Object.entries(quantities)) {
    if (quantity === 0) continue;
    const option = options.find((extra) => String(extra.ingrediente_id) === id);
    if (!option || !Number.isInteger(quantity) || quantity < 0 || quantity > option.max_por_item || removed.includes(option.nombre)) {
      throw new UserFacingError('Revisá los extras de la variante seleccionada.');
    }
    extras.push({ ...option, cantidad: quantity });
  }
  extras.sort((a, b) => a.ingrediente_id - b.ingrediente_id);
  const variant = product.variants?.find((item) => item.name === variantName);
  const basePrice = variant ? variant.price : product.price;
  const price = (Math.round(Number(basePrice) * 100) + extras.reduce((sum, extra) => sum + Math.round(Number(extra.precio) * 100) * extra.cantidad, 0)) / 100;
  const removals = [...removed].sort();
  return {
    ...product,
    id: `${product.id}-${JSON.stringify([variantName || '', removals, Number(basePrice), extras.map((extra) => [extra.ingrediente_id, extra.cantidad, Number(extra.precio), Number(extra.cantidad_requerida), extra.unidad_medida])])}`,
    productId: product.id,
    name: `${product.name}${variantName ? ` (${variantName})` : ''}`,
    variant: variantName || undefined,
    basePrice: Number(basePrice), price, extras,
    notes: removals.map((name) => `Sin ${name}`).join(', '),
  };
}
