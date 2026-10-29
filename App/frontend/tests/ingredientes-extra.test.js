import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildCustomizedItem, extrasForVariant, extrasLabel } from '../src/ordering/ingredientExtras.js';
import { mapOrder } from '../src/fulfillment/orderModel.js';

const cheese = { ingrediente_id: 3, nombre: 'Queso', unidad_medida: 'GR', cantidad_requerida: '30', precio: '750.10', max_por_item: 3, variantes: ['Simple', 'Doble'] };
const meat = { ingrediente_id: 4, nombre: 'Carne', unidad_medida: 'UNIDAD', cantidad_requerida: '1', precio: '2000.20', max_por_item: 2, variantes: ['Doble'] };
const product = { id: 7, name: 'Burger', price: 5000, extraOptions: [cheese, meat], variants: [{ name: 'Simple', price: 5000 }, { name: 'Doble', price: 7000 }] };

test('la comanda para cocina incluye nombre, cantidad y porción del snapshot', () => {
  const order = mapOrder({ estado: 'CONFIRMADO', tipo_entrega: 'RETIRO', items: [{ cantidad: 2, nombre_producto: 'Burger', extras: [{ ...cheese, cantidad: 1 }] }] });
  assert.match(order.items[0], /2x Burger.*1 × Queso.*30 g/);
});

test('ofrece únicamente extras de la variante y excluye dips', () => {
  assert.deepEqual(extrasForVariant(product, 'Simple'), [cheese]);
  assert.deepEqual(extrasForVariant({ ...product, category: 'Dips Extra' }, 'Doble'), []);
});
test('el total incluye porciones y conserva cantidades estructuradas y unidad real', () => {
  const item = buildCustomizedItem(product, 'Doble', [], { 3: 2, 4: 1 });
  assert.equal(item.price, 10500.40);
  assert.deepEqual(item.extras.map(({ ingrediente_id, cantidad }) => ({ ingrediente_id, cantidad })), [{ ingrediente_id: 3, cantidad: 2 }, { ingrediente_id: 4, cantidad: 1 }]);
  assert.match(extrasLabel(item.extras), /2 × Queso.*30 g/);
});
test('identidad estable distingue extras y retiros sin separar iguales', () => {
  const original = buildCustomizedItem(product, 'Doble', [], {});
  const extra = buildCustomizedItem(product, 'Doble', [], { 3: 1 });
  assert.notEqual(original.id, extra.id);
  assert.equal(extra.id, buildCustomizedItem(product, 'Doble', [], { 3: 1, 4: 0 }).id);
  assert.notEqual(original.id, buildCustomizedItem(product, 'Doble', ['Queso'], {}).id);
  assert.equal(buildCustomizedItem(product, 'Doble', ['Tomate', 'Queso'], {}).id, buildCustomizedItem(product, 'Doble', ['Queso', 'Tomate'], {}).id);
});
test('un cambio comercial no acumula el extra nuevo sobre un precio o porción anterior', () => {
  const original = buildCustomizedItem(product, 'Doble', [], { 3: 1 });
  for (const change of [{ precio: '1000' }, { cantidad_requerida: '60' }]) {
    const modified = { ...product, extraOptions: [{ ...cheese, ...change }, meat] };
    assert.notEqual(original.id, buildCustomizedItem(modified, 'Doble', [], { 3: 1 }).id);
  }
});
test('rechaza extras incompatibles, cantidades manipuladas y retiros contradictorios', () => {
  for (const quantities of [{ 4: 1 }, { 3: -1 }, { 3: 1.5 }, { 3: 4 }, { 99: 1 }]) {
    assert.throws(() => buildCustomizedItem(product, 'Simple', [], quantities));
  }
  assert.throws(() => buildCustomizedItem(product, 'Simple', ['Queso'], { 3: 1 }));
});
