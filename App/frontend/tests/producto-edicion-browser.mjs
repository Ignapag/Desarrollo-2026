// Solo API y PostgreSQL locales descartables. Escribe productos ficticios, nunca pedidos reales.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { chromium, request } = require(process.env.MONU_PLAYWRIGHT_PATH || 'playwright');
const origin = process.env.MONU_EDICION_URL || 'http://127.0.0.1:5181';
const apiOrigin = process.env.MONU_EDICION_API || 'http://127.0.0.1:8002';
for (const url of [origin, apiOrigin]) assert.ok(['127.0.0.1', 'localhost'].includes(new URL(url).hostname));
assert.equal(process.env.MONU_EDICION_BD_DESCARTABLE, '1', 'Verificar destino local descartable de la API');
const admin = await request.newContext({ baseURL: apiOrigin });
const api = async (method, url, data) => {
  const result = await admin.fetch(url, { method, data });
  assert.ok(result.ok(), `${method} ${url}: ${result.status()} ${await result.text()}`);
  return result.json();
};
const evidence = path.join(tmpdir(), `monu-edicion-browser-${Date.now()}`);
await mkdir(evidence, { recursive: true });
const report = { evidence, viewports: [], errors: [] };
const browser = await chromium.launch({ headless: true, ...(process.env.MONU_CHROMIUM_PATH ? { executablePath: process.env.MONU_CHROMIUM_PATH } : {}) });
const inputIngredient = (item) => ({ ingrediente_id: item.ingrediente_id, cantidad_requerida: item.cantidad_requerida, es_base: item.es_base });
const payload = (detail) => ({ nombre: detail.nombre, categoria_id: detail.categoria_id, descripcion: detail.descripcion, precio_base: detail.precio_base, imagen_url: detail.imagen_url, activo: detail.activo, orden: detail.orden, ingredientes: detail.ingredientes.map(inputIngredient), variantes: detail.variantes.map((variant) => ({ nombre: variant.nombre, precio: variant.precio, ingredientes: variant.ingredientes.map(inputIngredient) })), extras: detail.extras, actualizado_en_esperado: detail.actualizado_en });
try {
  await api('POST', '/api/auth/login', { username: 'demo1', password: 'Monu2026!' });
  const products = await api('GET', '/api/productos');
  const inventory = await api('GET', '/api/stock/ingredientes');
  const cheese = inventory.find((item) => item.nombre === 'Queso cheddar');
  const bread = inventory.find((item) => item.nombre === 'Pan de papa');
  assert.ok(cheese && bread);
  const photo = await readFile(new URL('../public/favicon.png', import.meta.url));
  const ingredients = (quantity) => [{ ingrediente_id: bread.id, cantidad_requerida: '1' }, { ingrediente_id: cheese.id, cantidad_requerida: quantity, es_base: false }];
  for (const [label, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    const name = `Burger ${label} ${Date.now()}`;
    const created = await api('POST', '/api/productos', { categoria_id: products.find((item) => item.categoria === 'Nuestras Burgers').categoria_id, nombre: name, precio_base: '10000', imagen_url: '/favicon.png', ingredientes: ingredients('25'), variantes: [{ nombre: 'Simple', precio: '10000', ingredientes: ingredients('25') }, { nombre: 'Doble', precio: '12000', ingredientes: ingredients('50') }], extras: [{ ingrediente_id: cheese.id, cantidad_requerida: '5', precio: '500', max_por_item: 2 }] });
    const context = await browser.newContext({ viewport, storageState: await admin.storageState(), locale: 'es-AR', reducedMotion: 'reduce' });
    const page = await context.newPage(); page.setDefaultTimeout(12000);
    page.on('pageerror', (error) => report.errors.push(error.message));
    await page.goto(`${origin}/dashboard/catalog?q=${encodeURIComponent(name)}`);
    await page.getByRole('button', { name: `Editar producto ${name}`, exact: true }).click();
    let dialog = page.getByRole('dialog', { name: `Editar producto: ${name}`, exact: true });
    await dialog.locator('#edit-product-name').fill(`${name} renovada`);
    await dialog.locator('#edit-product-description').fill('Receta y foto actualizadas');
    await dialog.locator('#edit-product-price').fill('10500,50');
    await dialog.locator('#edit-product-order').fill('4');
    await dialog.getByRole('textbox', { name: 'Variante 2', exact: true }).fill('Especial');
    const variantPrices = dialog.getByRole('textbox', { name: 'Precio ($)', exact: true });
    await variantPrices.nth(0).fill('11000'); await variantPrices.nth(1).fill('14500');
    const ingredientSelects = dialog.locator('select[id*="-ingredient-"]');
    let cheeseCard;
    for (let index = 0; index < await ingredientSelects.count(); index += 1) {
      if (await ingredientSelects.nth(index).inputValue() === String(cheese.id)) cheeseCard = ingredientSelects.nth(index).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]');
    }
    assert.ok(cheeseCard);
    await cheeseCard.getByRole('textbox', { name: /^Especial / }).fill('35');
    await cheeseCard.getByRole('spinbutton', { name: 'Máximo por hamburguesa', exact: true }).fill('3');
    const detailBefore = await api('GET', `/api/productos/${created.id}`);
    await dialog.locator('#edit-product-category').selectOption(String(detailBefore.categorias.find((item) => item.nombre === 'Combos').id));
    await dialog.locator('#edit-product-file').setInputFiles({ name: 'producto.png', mimeType: 'image/png', buffer: photo });
    await page.waitForFunction(() => document.querySelector('img[alt="Vista previa del producto"]')?.src.startsWith('data:image/png;base64,'));
    const box = await dialog.boundingBox(); assert.ok(box.width <= viewport.width - 30);
    await dialog.locator('#edit-product-name').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'edit-product-category');
    await page.screenshot({ path: path.join(evidence, `${label}-editor.png`), fullPage: true });
    const savedResponse = page.waitForResponse((response) => response.url() === `${apiOrigin}/api/productos/${created.id}` && response.request().method() === 'PUT');
    await dialog.getByRole('button', { name: 'Guardar producto', exact: true }).click();
    assert.equal((await savedResponse).status(), 200);
    await dialog.waitFor({ state: 'hidden' });
    let saved = await api('GET', `/api/productos/${created.id}`);
    assert.equal(saved.nombre, `${name} renovada`); assert.equal(Number(saved.precio_base), 10500.5);
    assert.equal(saved.categoria, 'Combos'); assert.equal(saved.orden, 4);
    assert.equal(saved.variantes[1].nombre, 'Especial'); assert.equal(Number(saved.variantes[1].precio), 14500);
    assert.equal(Number(saved.variantes[1].ingredientes.find((item) => item.ingrediente_id === cheese.id).cantidad_requerida), 35);
    assert.ok(saved.imagen_url.startsWith('data:image/png;base64,'));
    assert.equal(saved.extras.length, 1); assert.equal(saved.extras[0].max_por_item, 3);
    assert.equal((await api('GET', '/api/stock/ingredientes')).find((item) => item.id === cheese.id).cantidad_actual, cheese.cantidad_actual);
    const client = await browser.newContext({ viewport });
    const menu = await client.newPage(); menu.on('pageerror', (error) => report.errors.push(error.message));
    await menu.goto(`${origin}/menu?q=${encodeURIComponent(saved.nombre)}`);
    await menu.getByRole('heading', { name: saved.nombre, exact: true }).waitFor();
    await menu.getByRole('combobox', { name: `Variante de ${saved.nombre}` }).selectOption('Especial');
    assert.ok((await menu.locator('body').innerText()).includes('14500'));
    await menu.screenshot({ path: path.join(evidence, `${label}-menu.png`), fullPage: true });
    await client.close();
    // Otra persona guarda: el formulario viejo debe conservar sus cambios y rechazar el PUT.
    await page.getByRole('button', { name: `Editar producto ${saved.nombre}`, exact: true }).click();
    dialog = page.getByRole('dialog');
    await dialog.locator('#edit-product-name').fill('Borrador que debe conservarse');
    await api('PUT', `/api/productos/${created.id}`, { ...payload(saved), precio_base: '10600' });
    const conflict = page.waitForResponse((response) => response.url() === `${apiOrigin}/api/productos/${created.id}` && response.request().method() === 'PUT');
    await dialog.getByRole('button', { name: 'Guardar producto', exact: true }).click();
    assert.equal((await conflict).status(), 409);
    assert.equal(await dialog.locator('#edit-product-name').inputValue(), 'Borrador que debe conservarse');
    await dialog.getByRole('button', { name: 'Volver a cargar producto', exact: true }).click();
    await dialog.locator('#edit-product-name').waitFor();
    await page.waitForFunction((expected) => document.querySelector('#edit-product-name')?.value === expected, saved.nombre);
    await dialog.getByRole('button', { name: 'Quitar imagen del producto', exact: true }).click();
    await dialog.getByRole('checkbox', { name: 'Producto activo en el menú', exact: true }).uncheck();
    await dialog.getByRole('button', { name: 'Guardar producto', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    saved = await api('GET', `/api/productos/${created.id}`);
    assert.equal(saved.activo, false); assert.equal(saved.imagen_url, null);
    await page.getByRole('button', { name: 'Productos inactivos', exact: true }).click();
    await page.getByRole('button', { name: `Editar producto ${saved.nombre}`, exact: true }).click();
    dialog = page.getByRole('dialog');
    assert.equal(await dialog.getByRole('checkbox', { name: 'Producto activo en el menú', exact: true }).isChecked(), false);
    await dialog.locator('#edit-product-description').fill('Editado sin reactivarlo');
    await dialog.getByRole('button', { name: 'Guardar producto', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    saved = await api('GET', `/api/productos/${created.id}`);
    assert.equal(saved.activo, false); assert.equal(saved.descripcion, 'Editado sin reactivarlo');
    await page.screenshot({ path: path.join(evidence, `${label}-inactivo.png`), fullPage: true });
    report.viewports.push({ label, product: created.id, metadata: true, image: true, variants: true, recipe: true, extras: true, conflict: true, inactive: true, stockUnchanged: true });
    await context.close();
  }
  assert.deepEqual(report.errors, []);
} catch (error) {
  for (const [i, context] of browser.contexts().entries()) for (const [j, page] of context.pages().entries()) {
    await page.screenshot({ path: path.join(evidence, `fallo-${i}-${j}.png`), fullPage: true }).catch(() => undefined);
    await writeFile(path.join(evidence, `fallo-${i}-${j}.txt`), await page.locator('body').innerText().catch(() => ''));
  }
  throw error;
} finally {
  await writeFile(path.join(evidence, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close(); await admin.dispose(); console.log(JSON.stringify(report, null, 2));
}
