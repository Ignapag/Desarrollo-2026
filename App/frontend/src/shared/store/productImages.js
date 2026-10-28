// Fotografías originales provistas para los cinco dips sin imagen en el catálogo.
// Se resuelven en un solo lugar para el menú, el catálogo y el carrito.
const sauceImages = {
  alioli: '/images/salsas/alioli.webp',
  barbacoa: '/images/salsas/barbacoa.webp',
  mayonesa: '/images/salsas/mayonesa.webp',
  ketchup: '/images/salsas/ketchup.webp',
  mostaza: '/images/salsas/mostaza.webp',
};
const normalized = (value) => typeof value === 'string' ? value.trim().toLowerCase() : '';

export function productPhoto(product) {
  // Una imagen explícita de la API conserva prioridad sobre las fotos de respaldo.
  if (product.imagen_url) return { src: product.imagen_url, fit: 'cover' };
  const name = normalized(product.nombre);
  const sauce = normalized(product.categoria) === 'dips extra' && Object.hasOwn(sauceImages, name);
  return { src: sauce ? sauceImages[name] : null, fit: sauce ? 'contain' : 'cover' };
}
