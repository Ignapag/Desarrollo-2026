// Tope de unidades según stock: el catálogo informa cuántas unidades alcanzan para cada
// producto o variante. Es una guía para el cliente; el servidor revalida la demanda
// conjunta del carrito al crear el pedido.

// Unidades que admite el stock para el producto y la variante; null si no se informa.
export function stockLimit(product, variantName) {
  const source = variantName ? product?.variants?.find((variant) => variant.name === variantName) : product;
  return Number.isInteger(source?.maxUnits) ? source.maxUnits : null;
}

// Unidades del mismo producto y variante en el carrito, sumando todas sus personalizaciones.
export function unitsInCart(cart, productId, variantName) {
  return cart
    .filter((item) => (item.productId ?? item.id) === productId && (item.variant || '') === (variantName || ''))
    .reduce((sum, item) => sum + item.quantity, 0);
}

// Tope vigente de un ítem del carrito, tomado del catálogo actual si el producto sigue publicado.
export function cartItemLimit(catalog, item) {
  const productId = item.productId ?? item.id;
  return stockLimit(catalog.find((product) => product.id === productId) || item, item.variant);
}

export const unitsLabel = (units) => `${units} ${units === 1 ? 'unidad' : 'unidades'}`;
