import { UserFacingError } from '../shared/api/userErrors.js';
import { recipeFromApi, serializeRecipe } from './recipeModel.js';

export const MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024;
const imageTypes = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/avif']);

export function validateProductImageFile(file) {
  if (!file || !imageTypes.has(file.type)) return 'Elegí una imagen PNG, JPEG, WebP, GIF o AVIF.';
  if (file.size > MAX_PRODUCT_IMAGE_BYTES || file.size < 1) return 'La imagen debe pesar hasta 5 MiB y no estar vacía.';
  return null;
}

export function productEditFromApi(data) {
  if (!Number.isSafeInteger(data?.producto_id) || typeof data.nombre !== 'string' || !Number.isSafeInteger(data.categoria_id)
    || typeof data.activo !== 'boolean' || !Number.isInteger(data.orden) || !Number.isFinite(Number(data.precio_base))
    || !Number.isFinite(Date.parse(data.actualizado_en)) || !Array.isArray(data.categorias)) {
    throw new UserFacingError('No pudimos cargar los datos del producto. Volvé a intentarlo.');
  }
  return {
    fields: { name: data.nombre, description: data.descripcion || '', categoryId: String(data.categoria_id), price: String(data.precio_base), image: data.imagen_url || '', active: data.activo, order: String(data.orden) },
    recipe: recipeFromApi(data),
  };
}

export function serializeProductEdit(fields, recipe, original) {
  const name = fields.name.trim();
  if (!name || name.length > 120) throw new UserFacingError('Ingresá un nombre de hasta 120 caracteres.');
  const category = Number(fields.categoryId);
  const selectedCategory = original.categorias.find((option) => option.id === category);
  if (!selectedCategory) throw new UserFacingError('Seleccioná una categoría vigente.');
  const price = fields.price.trim().replace(',', '.');
  if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(price) || Number(price) <= 0) throw new UserFacingError('El precio base debe ser mayor que cero y tener hasta 2 decimales.');
  if (!/^\d+$/.test(fields.order) || Number(fields.order) > 2147483647) throw new UserFacingError('El orden debe ser un número entero entre 0 y 2147483647.');
  const image = fields.image.trim();
  if (image && (!/^(?:https?:\/\/|\/(?!\/)|data:image\/(?:png|jpeg|webp|gif|avif);base64,)/i.test(image) || image.includes('\\') || /\p{Cc}/u.test(image))) {
    throw new UserFacingError('Usá una URL de imagen http(s), una ruta del sitio o una foto raster.');
  }
  if (/^https?:/i.test(image)) {
    let url;
    try { url = new URL(image); } catch { throw new UserFacingError('La URL de imagen no es válida.'); }
    if (url.username || url.password) throw new UserFacingError('La URL de imagen no debe incluir credenciales.');
  }
  const effectiveRecipe = selectedCategory.nombre.trim().toLowerCase() === 'dips extra'
    ? { ...recipe, ingredients: recipe.ingredients.map((row) => ({ ...row, extraEnabled: false })) } : recipe;
  return { nombre: name, descripcion: fields.description.trim() || null, categoria_id: category, precio_base: price, imagen_url: image || null, activo: fields.active, orden: Number(fields.order), ...serializeRecipe(effectiveRecipe, { includePrices: true }), actualizado_en_esperado: original.actualizado_en };
}
