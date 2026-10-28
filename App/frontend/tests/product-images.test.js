import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { productPhoto } from '../src/shared/store/productImages.js';

const names = ['Alioli', 'Barbacoa', 'Mayonesa', 'Ketchup', 'Mostaza'];
test('los cinco dips usan su foto local y el archivo WebP existe', () => {
  const files = new Set();
  for (const nombre of names) {
    const photo = productPhoto({ nombre, categoria: 'Dips Extra', imagen_url: null });
    assert.deepEqual(photo, { src: '/images/salsas/' + nombre.toLowerCase() + '.webp', fit: 'contain' });
    const bytes = readFileSync(new URL('../public' + photo.src, import.meta.url));
    assert.equal(bytes.toString('ascii', 0, 4), 'RIFF');
    assert.equal(bytes.toString('ascii', 8, 12), 'WEBP');
    files.add(photo.src);
  }
  assert.equal(files.size, 5);
});
test('la imagen explícita de API tiene prioridad, sin cambiar el producto', () => {
  for (const nombre of names) {
    const product = Object.freeze({ nombre, categoria: 'Dips Extra', imagen_url: '/foto-propia.webp', precio_base: '900', activo: false });
    assert.deepEqual(productPhoto(product), { src: '/foto-propia.webp', fit: 'cover' });
  }
});
test('el respaldo se limita a los cinco nombres y su categoría', () => {
  for (const product of [{ nombre: 'Salsa Monu', categoria: 'Dips Extra' }, { nombre: 'Alioli', categoria: 'Bebidas' }, {}, { nombre: 'constructor', categoria: 'Dips Extra' }]) {
    assert.deepEqual(productPhoto(product), { src: null, fit: 'cover' });
  }
  assert.deepEqual(productPhoto({ nombre: ' ALIOLI ', categoria: ' DIPS EXTRA ' }), { src: '/images/salsas/alioli.webp', fit: 'contain' });
});
