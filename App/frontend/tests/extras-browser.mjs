// Recorrido real contra API + PostgreSQL descartables. Nunca usar con una base compartida.
// Requiere API y worker iniciados explícitamente con DATABASE_URL local y chat demo simulado.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { chromium, request } = require(process.env.MONU_PLAYWRIGHT_PATH || 'playwright');
const origin = process.env.MONU_EXTRAS_URL || 'http://127.0.0.1:5179';
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname), 'Solo URL local');
assert.equal(process.env.MONU_EXTRAS_BD_DESCARTABLE, '1', 'Confirmar API con base descartable mediante MONU_EXTRAS_BD_DESCARTABLE=1');
const evidence = path.join(tmpdir(), `monu-extras-browser-${Date.now()}`);
await mkdir(evidence, { recursive: true });
const report = { evidence, viewports: [], errors: [] };
const admin = await request.newContext({ baseURL: origin });
const api = async (method, url, data) => {
  const result = await admin.fetch(url, { method, data });
  assert.ok(result.ok(), `${method} ${url}: ${result.status()} ${await result.text()}`);
  return result.json();
};
const browser = await chromium.launch({ headless: true, ...(process.env.MONU_CHROMIUM_PATH ? { executablePath: process.env.MONU_CHROMIUM_PATH } : {}) });
try {
  await api('POST', '/api/auth/login', { username: 'demo1', password: 'Monu2026!' });
  const catalog = await api('GET', '/api/productos');
  const inventory = await api('GET', '/api/stock/ingredientes');
  const lettuce = inventory.find((item) => item.nombre === 'Lechuga');
  const meat = inventory.find((item) => item.nombre === 'Medallon de carne');
  const bread = inventory.find((item) => item.nombre === 'Pan de papa');
  assert.ok(lettuce && meat && bread);
  await api('POST', `/api/stock/ingredientes/${lettuce.id}/reposiciones`, { cantidad: '1000', origen: 'PRUEBA_EXTRAS_LOCAL' });
  const ingredients = (quantity) => [
    { ingrediente_id: bread.id, cantidad_requerida: '1' },
    { ingrediente_id: lettuce.id, cantidad_requerida: '10' },
    { ingrediente_id: meat.id, cantidad_requerida: quantity },
  ];
  const name = `Burger Extras Browser ${Date.now()}`;
  const product = await api('POST', '/api/productos', {
    categoria_id: catalog.find((item) => item.categoria === 'Nuestras Burgers').categoria_id,
    nombre: name, precio_base: '10000', ingredientes: ingredients('1'),
    variantes: [{ nombre: 'Simple', precio: '10000', ingredientes: ingredients('1') }, { nombre: 'Doble', precio: '12000', ingredientes: ingredients('2') }],
  });
  // Configurar extras desde el mismo formulario que usa el local.
  const staff = await browser.newContext({ storageState: await admin.storageState(), viewport: { width: 1440, height: 1000 } });
  const staffPage = await staff.newPage();
  staffPage.on('pageerror', (error) => report.errors.push(error.message));
  await staffPage.goto(`${origin}/dashboard/catalog?q=${encodeURIComponent(name)}`);
  await staffPage.getByRole('button', { name: `Editar receta de ${name}`, exact: true }).click();
  const recipe = staffPage.getByRole('dialog');
  await recipe.getByRole('checkbox', { name: 'Ofrecer Lechuga como extra', exact: true }).check();
  let row = recipe.locator('div.space-y-3.rounded-xl').filter({ has: staffPage.getByRole('checkbox', { name: 'Ofrecer Lechuga como extra', exact: true }) });
  await row.getByRole('textbox', { name: 'Porción por extra' }).fill('5');
  await row.getByRole('textbox', { name: 'Precio de venta' }).fill('750');
  await row.getByRole('spinbutton', { name: 'Máximo por hamburguesa' }).fill('2');
  await recipe.getByRole('checkbox', { name: 'Ofrecer Medallon de carne como extra', exact: true }).check();
  row = recipe.locator('div.space-y-3.rounded-xl').filter({ has: staffPage.getByRole('checkbox', { name: 'Ofrecer Medallon de carne como extra', exact: true }) });
  await row.getByRole('textbox', { name: 'Porción por extra' }).fill('1');
  await row.getByRole('textbox', { name: 'Precio de venta' }).fill('2000');
  await row.getByRole('spinbutton', { name: 'Máximo por hamburguesa' }).fill('2');
  await staffPage.screenshot({ path: path.join(evidence, 'configuracion.png'), fullPage: true });
  await recipe.getByRole('button', { name: 'Guardar receta', exact: true }).click();
  await recipe.waitFor({ state: 'hidden' });
  const configured = await api('GET', `/api/productos/${product.id}/receta`);
  assert.equal(configured.extras.length, 2);

  for (const [label, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport, locale: 'es-AR', reducedMotion: 'reduce' });
    const page = await context.newPage();
    page.on('pageerror', (error) => report.errors.push(error.message));
    await page.goto(`${origin}/menu?q=${encodeURIComponent(name)}`);
    await page.getByRole('heading', { name, exact: true }).waitFor();
    await page.getByText('Personalizar', { exact: true }).click();
    const addExtra = page.getByRole('button', { name: 'Sumar extra Lechuga', exact: true });
    await addExtra.focus();
    await addExtra.press('Enter');
    await page.getByRole('button', { name: 'Reducir extra Lechuga', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Sin Lechuga', exact: true }).check();
    await addExtra.click();
    assert.equal(await page.getByRole('checkbox', { name: 'Sin Lechuga', exact: true }).isChecked(), false);
    await addExtra.click();
    assert.equal(await addExtra.isDisabled(), true);
    await page.getByRole('button', { name: 'Reducir extra Lechuga', exact: true }).click();
    await page.getByRole('combobox', { name: `Variante de ${name}` }).selectOption('Doble');
    await page.getByRole('button', { name: 'Sumar extra Medallon de carne', exact: true }).click();
    assert.match(await page.locator('body').innerText(), /Total por hamburguesa: \$14\.750/);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const dimensions = await addExtra.boundingBox();
    assert.ok(dimensions.width >= 44 && dimensions.height >= 44);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(evidence, `${label}-menu.png`), fullPage: true });
    await page.getByRole('button', { name: `Agregar ${name} al carrito`, exact: true }).click();
    // Misma hamburguesa sin extras ocupa otra línea.
    await page.getByRole('button', { name: `Agregar ${name} al carrito`, exact: true }).click();
    await page.getByRole('button', { name: 'Abrir carrito, 2 productos', exact: true }).click();
    const cart = page.getByRole('dialog', { name: 'Tu pedido' });
    assert.match(await cart.innerText(), /1 × Lechuga/);
    assert.match(await cart.innerText(), /5 g cada extra/);
    await page.screenshot({ path: path.join(evidence, `${label}-carrito-productos.png`), fullPage: true });
    await cart.getByLabel('Nombre', { exact: true }).fill('Prueba');
    await cart.getByLabel('Apellido', { exact: true }).fill(label);
    await cart.getByLabel('Tu WhatsApp', { exact: true }).fill('2215559999');
    await cart.locator('#checkout-delivery').selectOption('RETIRO');
    await cart.locator('#checkout-payment').selectOption('EFECTIVO');
    await page.screenshot({ path: path.join(evidence, `${label}-carrito.png`), fullPage: true });
    await cart.getByRole('button', { name: 'Continuar en el chat', exact: true }).click();
    const log = page.getByRole('log', { name: 'Mensajes de la conversación' });
    await log.getByText(/Lechuga.*750/).first().waitFor({ timeout: 20000 });
    const send = async (message) => {
      await page.getByRole('textbox', { name: 'Tu mensaje' }).fill(message);
      await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click();
    };
    await send('confirmar');
    await log.getByText(/No hay un cambio pendiente/).first().waitFor({ timeout: 20000 });
    await page.screenshot({ path: path.join(evidence, `${label}-chat.png`), fullPage: true });
    // Leer pedido operativo y enviarlo a cocina por API con su versión real.
    const orders = await api('GET', '/api/pedidos?activos=true');
    const order = orders.find((candidate) => candidate.items.some((item) => item.producto_id === product.id) && candidate.items.some((item) => item.extras?.length));
    assert.ok(order, 'Pedido operativo con extras');
    const extraItem = order.items.find((item) => item.extras?.length);
    assert.equal(Number(extraItem.precio_unitario) + Number(extraItem.costo_opciones), 14750);
    assert.equal(extraItem.extras.length, 2);
    await api('PATCH', `/api/pedidos/${order.id}/estado`, { estado: 'EN_PREPARACION', version_esperada: order.version, motivo: 'Prueba navegador extras local' });
    await staffPage.goto(`${origin}/dashboard/kitchen`);
    await staffPage.getByText(/1 × Lechuga/).first().waitFor();
    await staffPage.screenshot({ path: path.join(evidence, `${label}-cocina.png`), fullPage: true });
    report.viewports.push({ label, product: product.id, order: order.id, configured: true, cart: true, chat: true, kitchen: true });
    await context.close();
  }
  assert.deepEqual(report.errors, []);
} catch (error) {
  for (const [index, context] of browser.contexts().entries()) {
    for (const [pageIndex, page] of context.pages().entries()) {
      await page.screenshot({ path: path.join(evidence, `fallo-${index}-${pageIndex}.png`), fullPage: true }).catch(() => undefined);
      await writeFile(path.join(evidence, `fallo-${index}-${pageIndex}.txt`), await page.locator('body').innerText().catch(() => 'Página no accesible'));
    }
  }
  throw error;
} finally {
  await writeFile(path.join(evidence, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
  await admin.dispose();
  console.log(JSON.stringify(report, null, 2));
}
