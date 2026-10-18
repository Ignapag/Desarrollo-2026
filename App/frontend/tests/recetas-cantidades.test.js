import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseRecipeQuantity, serializeRecipe, recipeFromApi } from '../src/management/recipeModel.js';

test('acepta decimales locales y fracciones generales con equivalencia exacta', () => {
  for (const [input, amount] of [['1/4', '0.25'], ['2/8', '0.25'], ['1/8', '0.125'], ['3/2', '1.5'], ['0,25', '0.25'], ['12.75', '12.75'], ['¼', '0.25']]) {
    const parsed = parseRecipeQuantity(input);
    assert.equal(parsed.amount, amount, input);
    assert.equal(parsed.approximate, false, input);
  }
});

test('una fracción no exacta muestra aproximación a tres decimales sin truncar en silencio', () => {
  const parsed = parseRecipeQuantity('2/3');
  assert.equal(parsed.amount, '0.667');
  assert.equal(parsed.approximate, true);
  assert.equal(parsed.display, '0,667');
});

test('rechaza cero, negativos, fracciones inválidas, precisión excesiva y desbordamiento', () => {
  for (const input of ['', '0', '-1', '1/0', '0/2', '1/10000', '1//2', 'NaN', 'Infinity', '1e2', '0,0001', '1000000000', '1.2.3']) assert.equal(parseRecipeQuantity(input).valid, false, input);
});

test('serializa todas las cantidades como decimales textuales y cada variante conserva su receta', () => {
  const recipe = { ingredients: [{ key: 'pan', ingredientId: '1', quantity: '1', quantities: ['1', '1'] }, { key: 'tomate', ingredientId: '2', quantity: '1/4', quantities: ['1/4', '1/2'] }], variants: [{ name: 'Simple', price: '11000' }, { name: 'Doble', price: '13000' }] };
  const payload = serializeRecipe(recipe, { includePrices: true });
  assert.deepEqual(payload.ingredientes.map((row) => row.cantidad_requerida), ['1', '0.25']);
  assert.deepEqual(payload.variantes[1].ingredientes.map((row) => row.cantidad_requerida), ['1', '0.5']);
  assert.equal(payload.variantes[1].precio, '13000');
  const edit = serializeRecipe(recipe);
  assert.equal(Object.hasOwn(edit.variantes[0], 'precio'), false);
});

test('una receta repetida o incompleta no se envía al servidor', () => {
  const row = { key: 'a', ingredientId: '1', quantity: '0.25', quantities: [] };
  assert.throws(() => serializeRecipe({ ingredients: [row, { ...row, key: 'b' }], variants: [] }), /repetir/i);
  assert.throws(() => serializeRecipe({ ingredients: [{ ...row, quantity: '1/0' }], variants: [] }), /cantidad/i);
});

test('editar conserva los valores y unidades de cada variante sin inferir multiplicadores', () => {
  const api = { ingredientes: [{ ingrediente_id: 1, nombre: 'Pan', unidad_medida: 'UNIDAD', cantidad_requerida: '1.000' }], variantes: [{ nombre: 'Simple', precio: '100', ingredientes: [{ ingrediente_id: 1, cantidad_requerida: '1.000' }] }, { nombre: 'Doble', precio: '150', ingredientes: [{ ingrediente_id: 1, cantidad_requerida: '1.000' }] }] };
  const form = recipeFromApi(api);
  assert.equal(form.ingredients[0].ingredientId, '1');
  assert.deepEqual(form.ingredients[0].quantities, ['1.000', '1.000']);
});
