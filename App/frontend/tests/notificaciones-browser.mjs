// Fixtures locales: no inicia backend, no usa credenciales ni escribe en una base.
// MONU_PLAYWRIGHT_PATH puede apuntar a Playwright instalado fuera del proyecto.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.MONU_PLAYWRIGHT_PATH || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidence = path.join(tmpdir(), 'monu-notificaciones-browser', Date.now() + '-' + process.pid);
await mkdir(evidence, { recursive: true });
const server = await createServer({ root, configFile: path.join(root, 'vite.config.ts'), mode: 'personal',
  cacheDir: path.join(root, 'node_modules/.vite-tests/notificaciones-browser-' + process.pid),
  plugins: [{ name: 'notificaciones-sin-backend', configResolved(config) { config.server.proxy = {}; } }],
  server: { host: '127.0.0.1', port: 0, hmr: false, open: false },
});
let browser;
const report = { fixturesOnly: true, results: [], pageErrors: [], writes: [], unknownRequests: [] };
const user = { id: 1, username: 'operador-fixture', nombre: 'Operador', apellido: 'Prueba', rol: 'EMPLEADO', permisos: ['pedidos.ver', 'stock.ver', 'whatsapp.ver'] };
const inventory = [
  { id: 3, nombre: 'Pan', unidad_medida: 'UNIDAD', cantidad_actual: '0', umbral_minimo: '10', nivel: 'SIN_STOCK', activo: true },
  { id: 4, nombre: 'Queso', unidad_medida: 'KG', cantidad_actual: '2', umbral_minimo: '5', nivel: 'BAJO_UMBRAL', activo: true },
];
const makeInbox = () => ({
  comprobantes: [
    { id: 5, pedido_id: 125, numero: 125, total: '1000', metodo_pago: 'TRANSFERENCIA', estado: 'PENDIENTE', creado_en: new Date(Date.now() - 300000).toISOString() },
    { id: 7, pedido_id: 127, numero: 127, total: '1000', metodo_pago: 'TRANSFERENCIA', estado: 'APROBADO', creado_en: '2026-10-27T18:00:00-03:00' },
  ],
  atenciones: [{ id: 6, estado: 'PENDIENTE', motivo: 'SOLICITUD', pedido_id: null, telefono: null, cliente: 'Cliente de prueba', productos: [], mensajes: [], respuestas: [], mensaje: 'Necesito ayuda', creado_en: new Date().toISOString() }],
  cambios: [], salidas: [],
});
try {
  await server.listen();
  const origin = 'http://127.0.0.1:' + server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, ...(process.env.MONU_CHROMIUM_PATH ? { executablePath: process.env.MONU_CHROMIUM_PATH } : {}) });
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }, { width: 320, height: 740 }]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    page.on('pageerror', (error) => report.pageErrors.push(error.message));
    let fail = false;
    let currentUser = user;
    let inbox = makeInbox();
    const calls = [];
    await context.route('**/*', async (route) => {
      const request = route.request(); const url = new URL(request.url());
      if (url.origin !== origin) return route.abort();
      if (!url.pathname.startsWith('/api/')) return route.continue();
      calls.push(url.pathname);
      if (request.method() !== 'GET') { report.writes.push(url.pathname); return route.abort(); }
      let body;
      if (url.pathname === '/api/auth/me') body = currentUser;
      else if (url.pathname === '/api/pedidos') body = [];
      else if (url.pathname === '/api/stock/ingredientes') body = inventory;
      else if (url.pathname === '/api/whatsapp/bandeja') {
        if (fail) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'detalle privado que no debe mostrarse' }) });
        body = inbox;
      } else { report.unknownRequests.push(url.pathname); return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }); }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(origin + '/dashboard/orders');
    const bell = () => page.getByRole('button', { name: /^Notificaciones(?::|$)/ });
    await page.getByRole('button', { name: 'Notificaciones: 5 sin leer', exact: true }).waitFor();
    await bell().click();
    const dialog = page.getByRole('dialog', { name: 'Notificaciones' });
    await dialog.waitFor();
    await dialog.getByRole('heading', { name: 'Pan agotado', exact: true }).waitFor();
    assert.equal(await dialog.locator('li').count(), 4);
    const box = await dialog.boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= viewport.width, 'El panel entra en la pantalla');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Sin desborde horizontal');
    // El diálogo nativo mantiene el foco en su contenido al navegar por teclado.
    for (let index = 0; index < 18; index += 1) { await page.keyboard.press('Tab'); assert.ok(await dialog.evaluate((element) => element.contains(document.activeElement))); }
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'detached' });
    assert.ok(await bell().evaluate((element) => element === document.activeElement));
    await page.keyboard.press('Enter'); await dialog.waitFor();
    await dialog.getByRole('button', { name: 'Marcar todas como leídas', exact: true }).click();
    await page.getByRole('button', { name: 'Notificaciones', exact: true }).waitFor();
    assert.equal(await dialog.locator('li').count(), 4, 'Leer no resuelve los pendientes');
    await dialog.getByRole('button', { name: 'Todas', exact: true }).click();
    await dialog.getByRole('heading', { name: 'Comprobante revisado', exact: true }).waitFor();
    assert.equal(await dialog.locator('li').count(), 5);
    await page.screenshot({ path: path.join(evidence, viewport.width + '-panel.png'), fullPage: true });
    await dialog.getByRole('button', { name: 'Pendientes', exact: true }).click();
    // Los accesos abren y enfocan el registro concreto.
    await dialog.getByRole('link', { name: 'Abrir ingrediente', exact: true }).first().click();
    await page.locator('#ingrediente-3').waitFor();
    await page.waitForFunction(() => document.activeElement?.id === 'ingrediente-3');
    await bell().click();
    await dialog.getByRole('link', { name: 'Revisar comprobante', exact: true }).click();
    await page.locator('#whatsapp-comprobantes-5').waitFor();
    await page.waitForFunction(() => document.activeElement?.id === 'whatsapp-comprobantes-5');
    await bell().click();
    await dialog.getByRole('link', { name: 'Abrir conversación', exact: true }).click();
    await page.locator('#whatsapp-atencion-6').waitFor();
    await page.waitForFunction(() => document.activeElement?.id === 'whatsapp-atencion-6');
    // Al recargar, la lectura sigue perteneciendo a este usuario.
    await page.reload(); await page.getByRole('button', { name: 'Notificaciones', exact: true }).waitFor();
    await bell().click();
    fail = true;
    await dialog.getByRole('button', { name: 'Actualizar notificaciones', exact: true }).click();
    await dialog.getByText('La información disponible puede estar desactualizada.', { exact: true }).waitFor();
    assert.equal(await dialog.locator('li').count(), 4);
    assert.equal(await dialog.getByText('detalle privado que no debe mostrarse', { exact: false }).count(), 0);
    fail = false;
    await dialog.getByRole('button', { name: 'Reintentar', exact: true }).click();
    await dialog.getByText('La información disponible puede estar desactualizada.', { exact: true }).waitFor({ state: 'detached' });
    await dialog.getByRole('button', { name: 'Cerrar notificaciones', exact: true }).click();
    // Mismo navegador, otra cuenta y sin permisos de inventario ni pedidos.
    currentUser = { ...user, id: 2, permisos: ['whatsapp.ver'] };
    await page.reload();
    await page.getByRole('button', { name: 'Notificaciones: 3 sin leer', exact: true }).waitFor();
    await bell().click();
    assert.equal(await dialog.getByRole('link').count(), 0);
    assert.equal(await dialog.getByRole('heading', { name: 'Pan agotado' }).count(), 0);
    assert.equal(calls.includes('/api/whatsapp/avisos'), false, 'Sin segundo sondeo del resumen');
    const saved = await page.evaluate(() => Object.entries(localStorage).filter(([key]) => key.startsWith('monu.notifications.read.v1:')));
    assert.ok(saved.every(([, value]) => !/Cliente|pedido_id|telefono|Necesito/.test(value)), 'El almacenamiento no contiene mensajes ni datos privados');
    report.results.push({ viewport: viewport.width, keyboard: true, destinations: true, readState: true, permissions: true, errorRetry: true });
    await context.close();
  }
  assert.deepEqual(report.pageErrors, []);
  assert.deepEqual(report.writes, []);
  assert.deepEqual(report.unknownRequests, []);
} catch (error) {
  report.failure = error.message;
  throw error;
} finally {
  await writeFile(path.join(evidence, 'report.json'), JSON.stringify(report, null, 2));
  await browser?.close(); await server.close();
  console.log('Evidencias: ' + evidence);
}
