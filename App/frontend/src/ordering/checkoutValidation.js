// Límites de BorradorEntrada / ItemPedidoEntrada / DireccionPedidoEntrada.
// Precios, stock y disponibilidad se vuelven a validar exclusivamente en la API.
export function validateCheckout(payload, { partial = false } = {}) {
  if (!payload.items.length || payload.items.length > 50) return { message: 'El pedido debe incluir entre 1 y 50 productos.' };
  for (const item of payload.items) {
    if (!Number.isSafeInteger(item.producto_id) || item.producto_id <= 0) return { message: 'Hay un producto inválido. Quitalo y volvé a elegirlo del menú.' };
    if (!Number.isInteger(item.cantidad) || item.cantidad < 1 || item.cantidad > 50) return { message: 'Cada producto admite entre 1 y 50 unidades enteras. Revisá las cantidades.' };
    if ((item.variante && item.variante.length > 60) || (item.aclaraciones && item.aclaraciones.length > 500)) return { message: 'La personalización supera el límite del pedido. Revisá el producto en el menú.' };
  }
  if (!partial) {
    for (const [key, label] of [['nombre', 'nombre'], ['apellido', 'apellido']]) {
      if (!payload.contacto?.[key]?.trim() || payload.contacto[key].length > 80) return { field: `checkout-${key === 'nombre' ? 'first-name' : 'last-name'}`, message: `Ingresá tu ${label}, hasta 80 caracteres.` };
    }
    if (!/^[0-9]{11,15}$/.test(payload.contacto?.telefono || '')) return { field: 'checkout-phone', message: 'Ingresá código de área y número, sin 0 ni 15.' };
  }
  if (payload.tipo_entrega === 'DELIVERY' && (!partial || payload.direccion_nueva)) {
    for (const [key, field, label, max] of [['calle', 'street', 'la calle', 160], ['numero', 'number', 'el número', 30], ['localidad', 'zone', 'la localidad', 100]]) {
      if (!payload.direccion_nueva?.[key]?.trim() || payload.direccion_nueva[key].length > max) return { field: `checkout-${field}`, message: `Completá ${label}, hasta ${max} caracteres.` };
    }
  }
  return null;
}
