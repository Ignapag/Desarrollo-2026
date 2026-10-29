import assert from 'node:assert/strict';
import { test } from 'node:test';
import { productEditFromApi, serializeProductEdit, validateProductImageFile } from '../src/management/productEditorModel.js';

const detail = { producto_id: 8, nombre: 'Cheese', descripcion: 'Original', categoria_id: 1, categoria: 'Burgers', precio_base: '10000', imagen_url: '/cheese.png', activo: false, orden: 2, actualizado_en: '2026-10-29T12:00:00Z', categorias: [{ id: 1, nombre: 'Burgers', activa: true }], ingredientes: [{ ingrediente_id: 3, nombre: 'Queso', unidad_medida: 'GR', cantidad_requerida: '25', es_base: false }], variantes: [], extras: [] };

test('carga el producto real completo, imagen y estado inactivo sin reactivarlo', () => {
  const { fields, recipe } = productEditFromApi(detail);
  assert.equal(fields.name, 'Cheese');
  assert.equal(fields.image, '/cheese.png');
  assert.equal(fields.active, false);
  assert.equal(recipe.ingredients[0].quantity, '25');
});
test('guarda metadatos, receta y versión juntos y quitar imagen envía null', () => {
  const { fields, recipe } = productEditFromApi(detail);
  const payload = serializeProductEdit({ ...fields, name: ' Nueva ', price: '12500,50', image: '', order: '3' }, recipe, detail);
  assert.equal(payload.nombre, 'Nueva');
  assert.equal(payload.precio_base, '12500.50');
  assert.equal(payload.imagen_url, null);
  assert.equal(payload.activo, false);
  assert.equal(payload.orden, 3);
  assert.equal(payload.actualizado_en_esperado, detail.actualizado_en);
  assert.equal(payload.ingredientes[0].cantidad_requerida, '25');
});
test('valida nombre, precio, categoría, orden e imagen antes del envío', () => {
  const { fields, recipe } = productEditFromApi(detail);
  for (const invalid of [{ name: '  ' }, { price: '0' }, { price: '1.234' }, { categoryId: '99' }, { order: '1.5' }, { order: '-1' }, { image: 'javascript:alert(1)' }, { image: 'data:image/svg+xml,<svg />' }]) {
    assert.throws(() => serializeProductEdit({ ...fields, ...invalid }, recipe, detail));
  }
});
test('acepta fotos raster pequeñas y rechaza SVG, archivos ajenos y más de 5 MiB', () => {
  assert.equal(validateProductImageFile({ type: 'image/png', size: 100 }), null);
  for (const file of [{ type: 'image/svg+xml', size: 100 }, { type: 'text/html', size: 10 }, { type: 'image/png', size: 6 * 1024 * 1024 }]) assert.ok(validateProductImageFile(file));
});
test('cambiar a Dips Extra elimina extras ocultos de la configuración enviada', () => {
  const original = { ...detail, categorias: [...detail.categorias, { id: 4, nombre: 'Dips Extra', activa: true }] };
  const { fields, recipe } = productEditFromApi(original);
  recipe.ingredients[0].extraEnabled = true;
  recipe.ingredients[0].extraPrice = '500';
  recipe.ingredients[0].extraPortion = '5';
  recipe.ingredients[0].extraMax = '2';
  assert.deepEqual(serializeProductEdit({ ...fields, categoryId: '4' }, recipe, original).extras, []);
});
